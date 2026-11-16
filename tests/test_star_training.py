import hashlib
import io
import sys
import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'airflow/dags'))
from star_training.workflow import prepare_data, read_snapshot, compare_and_promote
from star_training.features import D2_FEATURES


class Predictor:
    feature_names_in_ = np.array(D2_FEATURES)

    def __init__(self, predictions):
        self.predictions = predictions

    def predict(self, frame):
        return np.array(self.predictions)


def sample_csv():
    rows = []
    for i in range(90):
        rows.append({'objid': str(1237645879551000000+i), 'class': ['GALAXY','QSO','STAR'][i%3],
                     **{b: 15+i%3+j/10+i/1000 for j,b in enumerate(['u','g','r','i','z'])}})
    return pd.DataFrame(rows).to_csv(index=False).encode()


class TrainingTests(unittest.TestCase):
    def test_knn_can_be_bounded_to_small_cv_training_folds(self):
        import optuna
        from star_training.features import make_pipeline
        from sklearn.model_selection import cross_val_score,StratifiedKFold
        frame=pd.DataFrame(np.arange(216).reshape(24,9),columns=D2_FEATURES)
        labels=np.array(['GALAXY','QSO','STAR']*8)
        trial=optuna.trial.FixedTrial({'classifier':'KNN','knn_neighbors':19,
                                      'knn_weights':'uniform','knn_p':2})
        pipe=make_pipeline(trial,max_neighbors=19)
        scores=cross_val_score(pipe,frame,labels,cv=StratifiedKFold(5),
                               scoring='f1_weighted',error_score='raise')
        self.assertEqual(len(scores),5)

    def test_completed_stage_is_not_executed_twice(self):
        import json
        from botocore.exceptions import ClientError
        from star_training.orchestration import stage
        objects={}
        s3=Mock()
        def get(**kw):
            if kw['Key'] not in objects:
                raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
            return {'Body':io.BytesIO(objects[kw['Key']])}
        s3.get_object.side_effect=get
        s3.put_object.side_effect=lambda **kw: objects.update({kw['Key']:kw['Body']})
        compute=Mock(return_value={'version':'2'})
        with patch('star_training.orchestration.runtime',return_value=(s3,Mock())):
            self.assertEqual(stage({'prefix':'run'},'registered',compute),{'version':'2'})
            self.assertEqual(stage({'prefix':'run'},'registered',compute),{'version':'2'})
        compute.assert_called_once()

    def test_checkpoint_connection_error_is_not_treated_as_absent(self):
        from star_training.orchestration import read_json
        s3=Mock();s3.get_object.side_effect=ConnectionError('MinIO')
        with self.assertRaises(ConnectionError):read_json(s3,'checkpoint')

    def test_split_is_repeatable_preserves_ids_and_never_scales_raw(self):
        raw = sample_csv()
        a, b = prepare_data(raw), prepare_data(raw)
        pd.testing.assert_frame_equal(a.X_train,b.X_train)
        self.assertTrue(set(a.train_objids).isdisjoint(a.test_objids))
        self.assertEqual(a.train_objids[0][:10], '1237645879')
        self.assertGreater(a.X_train.u.mean(), 10)
        self.assertEqual(a.sha256, hashlib.sha256(raw).hexdigest())

    def test_snapshot_checksum_mismatch_is_rejected(self):
        s3 = Mock()
        s3.get_object.return_value = {'Body':io.BytesIO(sample_csv())}
        with self.assertRaisesRegex(ValueError,'SHA'):
            read_snapshot(s3, {'bucket':'data','key':'raw/star/snapshots/x.csv','sha256':'0'*64})

    def scenario(self, candidate_predictions, champion_predictions=None, version='1'):
        data = SimpleNamespace(X_test=pd.DataFrame(np.zeros((3,9)),columns=D2_FEATURES),
                               y_test=pd.Series(['GALAXY','QSO','STAR']), sha256='a'*64,seed=42)
        client = Mock()
        client.get_registered_model.return_value = SimpleNamespace(aliases={} if version is None else {'champion':version})
        loader = Mock(side_effect=[Predictor(candidate_predictions)] +
                      ([] if version is None else [Predictor(champion_predictions)]))
        candidate = {'name':'star_type_model_prod','version':'2','run_id':'run2',
                     'model_uri':'models:/candidate','sha256':data.sha256,'seed':42}
        return data,client,loader,candidate

    def test_better_candidate_promoted_and_both_evaluated_on_same_frame(self):
        d,c,l,m = self.scenario(['GALAXY','QSO','STAR'],['GALAXY','GALAXY','GALAXY'])
        new,old=Predictor(['GALAXY','QSO','STAR']),Predictor(['GALAXY']*3)
        new.predict=Mock(wraps=new.predict);old.predict=Mock(wraps=old.predict)
        l.side_effect=[new,old]
        result=compare_and_promote(d,m,client=c,loader=l)
        self.assertTrue(result['promoted'])
        c.set_registered_model_alias.assert_called_once_with(m['name'],'champion','2')
        self.assertEqual(l.call_args_list[1].args[0], 'models:/star_type_model_prod/1')
        self.assertEqual(result['candidate_f1_weighted'],1.0)
        self.assertIs(new.predict.call_args.args[0],d.X_test)
        self.assertIs(old.predict.call_args.args[0],d.X_test)

    def test_tie_or_worse_keeps_existing_champion(self):
        for candidate in [['GALAXY','QSO','STAR'],['GALAXY','GALAXY','GALAXY']]:
            with self.subTest(candidate=candidate):
                d,c,l,m=self.scenario(candidate,['GALAXY','QSO','STAR'])
                result=compare_and_promote(d,m,client=c,loader=l)
                self.assertFalse(result['promoted'])
                c.set_registered_model_alias.assert_not_called()

    def test_first_valid_candidate_becomes_champion(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],version=None)
        self.assertTrue(compare_and_promote(d,m,client=c,loader=l)['promoted'])
        c.set_registered_model_alias.assert_called_once()

    def test_champion_download_failure_does_not_promote(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        l.side_effect=[Predictor(['GALAXY','QSO','STAR']),ConnectionError('MinIO')]
        with self.assertRaises(ConnectionError):compare_and_promote(d,m,client=c,loader=l)
        c.set_registered_model_alias.assert_not_called()

    def test_schema_mismatch_does_not_promote(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        p=Predictor(['GALAXY']*3);p.feature_names_in_=np.array(['redshift'])
        l.side_effect=[p]
        with self.assertRaisesRegex(ValueError,'esquema'):compare_and_promote(d,m,client=c,loader=l)
        c.set_registered_model_alias.assert_not_called()

    def test_alias_change_during_comparison_blocks_promotion(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        c.get_registered_model.side_effect=[SimpleNamespace(aliases={'champion':'1'}),
                                          SimpleNamespace(aliases={'champion':'3'})]
        with self.assertRaisesRegex(RuntimeError,'cambió'):compare_and_promote(d,m,client=c,loader=l)
        c.set_registered_model_alias.assert_not_called()

    def test_repeated_promotion_of_current_version_does_not_write_alias(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],version='2')
        result=compare_and_promote(d,m,client=c,loader=l)
        self.assertEqual(result['reason'],'already_champion')
        c.set_registered_model_alias.assert_not_called()

    def test_retry_repairs_tags_after_alias_was_updated_and_preserves_decision(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        aliases={'champion':'1'}
        tags={}
        c.get_registered_model.side_effect=lambda name:SimpleNamespace(aliases=dict(aliases))
        c.set_registered_model_alias.side_effect=lambda name,alias,v:aliases.update({alias:v})
        c.get_run.return_value=SimpleNamespace(data=SimpleNamespace(tags=tags))
        c.set_tag.side_effect=lambda run,key,value:tags.update({key:value})
        c.set_model_version_tag.side_effect=ConnectionError('tag write failed after promotion')
        with tempfile.TemporaryDirectory() as folder:
            audit=Path(folder)/'comparison.json'
            c.log_dict.side_effect=lambda run,result,path:audit.write_text(json.dumps(result))
            c.download_artifacts.return_value=str(audit)
            with self.assertRaises(ConnectionError):compare_and_promote(d,m,client=c,loader=l)
            self.assertEqual(aliases['champion'],'2')
            c.set_model_version_tag.side_effect=None
            result=compare_and_promote(d,m,client=c,loader=l)
            self.assertTrue(result['promoted'])
            self.assertEqual(result['reason'],'improved')
            self.assertEqual(result['champion_f1_weighted'],.16666666666666666)
            self.assertEqual(tags['promotion_result'],'improved')
            self.assertEqual(c.set_registered_model_alias.call_count,1)

    def test_different_dataset_is_rejected(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        m['sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'dataset'):compare_and_promote(d,m,client=c,loader=l)
        c.set_registered_model_alias.assert_not_called()

    def test_different_split_is_rejected(self):
        d,c,l,m=self.scenario(['GALAXY','QSO','STAR'],['GALAXY']*3)
        m['seed']=3
        with self.assertRaisesRegex(ValueError,'split'):compare_and_promote(d,m,client=c,loader=l)
        c.set_registered_model_alias.assert_not_called()


if __name__=='__main__':unittest.main()
