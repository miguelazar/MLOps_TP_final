import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import cross_val_score, StratifiedKFold

ROOT = Path(__file__).resolve().parent
if (ROOT / 'stellar').exists():
    sys.path.insert(0, str(ROOT / 'stellar'))
else:
    sys.path.insert(0, str(ROOT.parent / 'notebooks'))
    sys.path.insert(0, str(ROOT.parent / 'airflow' / 'dags'))
from star_workflow import prepare_d2, make_pipeline, BANDS, D2_FEATURES
from star_sdss_source import parse_sdss_csv


class StarTests(unittest.TestCase):
    def test_cleaning_and_d2(self):
        df = pd.DataFrame({
            'objid': ['1237645879551000764', '1237645879551000764', '2', '3', '4'],
            'class': ['STAR', 'STAR', 'GALAXY', 'QSO', 'STAR'],
            'u': [20, 20, -9999, np.nan, 25],
            'g': [18, 18, 19, 19, 22], 'r': [17, 17, 18, 18, 20],
            'i': [16, 16, 17, 17, 19], 'z': [15, 15, 16, 16, 18],
            'redshift': [0, 0, .1, 1, 0], 'ra': [1]*5, 'dec': [2]*5})
        clean = prepare_d2(df)
        self.assertEqual(list(clean.objid), ['1237645879551000764', '4'])
        self.assertEqual(clean.loc[0, 'u-g'], 2)
        self.assertEqual(len(D2_FEATURES), 9)
        self.assertNotIn('redshift', D2_FEATURES)
        pd.testing.assert_frame_equal(clean, prepare_d2(df))
        self.assertEqual(df.u.iloc[2], -9999)

    def test_csv_preserves_ids_and_rejects_errors(self):
        csv = '#Table1\nobjid,ra,dec,u,g,r,i,z,class,redshift\n1237645879551000764,1,2,20,19,18,17,16,STAR,0\n'
        payload, rows = parse_sdss_csv(csv)
        self.assertIn(b'1237645879551000764', payload)
        self.assertEqual(rows, 1)
        for invalid in ['<html>Error</html>', '#Table1\nobjid,class\n1,STAR', csv.split('123764')[0]]:
            with self.assertRaises(ValueError):
                parse_sdss_csv(invalid)

    def test_scaler_is_fit_inside_each_fold(self):
        import optuna
        x = pd.DataFrame(np.arange(270).reshape(30, 9), columns=D2_FEATURES)
        y = np.array(['GALAXY', 'QSO', 'STAR'] * 10)
        pipe = make_pipeline(optuna.trial.FixedTrial({'classifier':'SVC_linear', 'svc_c':1.0}))
        scores = cross_val_score(pipe, x, y, cv=StratifiedKFold(5), scoring='f1_weighted', n_jobs=1)
        self.assertEqual(len(scores), 5)
        self.assertFalse(hasattr(pipe['scaler'], 'mean_'))
        pipe.fit(x, y)
        np.testing.assert_allclose(pipe['scaler'].mean_, x.mean())


if __name__ == '__main__':
    unittest.main()
