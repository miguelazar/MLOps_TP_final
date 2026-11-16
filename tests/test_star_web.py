import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'star_web' if (HERE / 'star_web').exists()
                       else HERE.parent / 'star_web'))
from core import parse_objects, validate_features, FEATURES


class StarWebTests(unittest.TestCase):
    def test_object_ids_and_missing_measurements(self):
        text = ('#Table1\nobjid,ra,dec,u,g,r,i,z,class,redshift\n'
                '1237645879551000764,1,2,20,19,18,17,16,STAR,0\n'
                '2,1,2,-9999,19,18,17,16,STAR,0\n')
        result = parse_objects(text)
        self.assertEqual(result['objects'][0]['objid'], '1237645879551000764')
        self.assertEqual(result['received'], 2)
        self.assertEqual(result['excluded'], 1)

    def test_d2_order_and_validation(self):
        features = dict(u=20, g=19, r=18, i=17, z=16)
        features.update({'u-g':1, 'g-r':1, 'r-i':1, 'i-z':1})
        self.assertEqual(list(validate_features(features)), FEATURES)
        for bad in [dict(features, **{'u-g':99}), dict(features, u=float('nan')),
                    dict(features, redshift=1), {'u':20}]:
            with self.assertRaises(ValueError):
                validate_features(bad)

    def test_api_roundtrip_and_bad_features_never_predict(self):
        from fastapi.testclient import TestClient
        from app import create_app
        calls = []
        def predict(features):
            calls.append(features)
            return {'prediction':'STAR', 'model_version':'1', 'model_name':'star_type_model_prod'}
        client = TestClient(create_app(source=lambda refresh: {'objects':[], 'received':0, 'excluded':0},
                                       predictor=predict))
        self.assertEqual(client.get('/').status_code, 200)
        self.assertEqual(client.get('/api/objects').json()['objects'], [])
        self.assertEqual(client.post('/api/predict', json={'features':{'u':20}}).status_code, 422)
        self.assertEqual(calls, [])
        f = dict(u=20, g=19, r=18, i=17, z=16)
        f.update({'u-g':1, 'g-r':1, 'r-i':1, 'i-z':1})
        response = client.post('/api/predict', json={'features':f})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['prediction'], 'STAR')
        self.assertEqual(list(calls[0]), FEATURES)
        response = client.post('/api/predict', json={'features':dict(f, **{'u-g':True})})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
