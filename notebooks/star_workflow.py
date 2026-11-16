"""Preparación D2 y modelos para la notebook de clasificación estelar."""
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier

BANDS = ['u', 'g', 'r', 'i', 'z']
COLORS = ['u-g', 'g-r', 'r-i', 'i-z']
D2_FEATURES = BANDS + COLORS
CLASSES = ['GALAXY', 'QSO', 'STAR']


def prepare_d2(frame):
    required = {'objid', 'class', *BANDS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'Faltan columnas: {sorted(missing)}')
    df = frame.copy().drop_duplicates('objid', keep='first')
    df['class'] = df['class'].astype('string').str.strip().str.upper()
    for band in BANDS:
        df[band] = pd.to_numeric(df[band], errors='coerce')
    valid = (np.isfinite(df[BANDS]).all(axis=1)
             & (df[BANDS] > -9000).all(axis=1)
             & df['class'].isin(CLASSES))
    df = df.loc[valid].copy()
    if df.empty:
        raise ValueError('No quedaron observaciones válidas para D2')
    for left, right in zip(BANDS[:-1], BANDS[1:]):
        df[f'{left}-{right}'] = df[left] - df[right]
    return df.reset_index(drop=True)


def make_pipeline(trial):
    name = trial.suggest_categorical('classifier', [
        'SVC_linear', 'SVC_poly', 'SVC_rbf', 'DecisionTree', 'RandomForest', 'KNN'])
    if name.startswith('SVC_'):
        kernel = name.split('_', 1)[1]
        params = {'C': trial.suggest_float('svc_c', .01, 100, log=True),
                  'kernel': kernel, 'gamma': 'scale', 'random_state': 42}
        if kernel == 'poly':
            params['degree'] = trial.suggest_int('svc_degree', 2, 6)
        estimator = SVC(**params)
    elif name == 'DecisionTree':
        estimator = DecisionTreeClassifier(
            max_depth=trial.suggest_int('tree_max_depth', 2, 32), random_state=42)
    elif name == 'RandomForest':
        estimator = RandomForestClassifier(
            max_depth=trial.suggest_int('rf_max_depth', 2, 32),
            n_estimators=trial.suggest_int('rf_n_estimators', 30, 150),
            random_state=42, n_jobs=1)
    else:
        estimator = KNeighborsClassifier(
            n_neighbors=trial.suggest_int('knn_neighbors', 3, 25),
            weights=trial.suggest_categorical('knn_weights', ['uniform', 'distance']),
            p=trial.suggest_int('knn_p', 1, 2), n_jobs=1)
    return Pipeline([('scaler', StandardScaler()), ('classifier', estimator)])
