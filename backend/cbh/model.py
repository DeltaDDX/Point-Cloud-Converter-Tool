import pickle

import numpy as np


class CBHModel:
    """
    Random forest wrapper for CBH training and inference.
    """

    def __init__(self, estimator=None, random_state=42, feature_names=None, **forest_kwargs):
        self.random_state = random_state
        self.forest_kwargs = forest_kwargs
        self.estimator = estimator
        self.feature_names = list(feature_names) if feature_names is not None else None

    def train(self, X, y):
        X = _validate_feature_matrix(X)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim != 1:
            raise ValueError("y must be a 1D target array")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X and y must contain the same number of rows")

        if self.estimator is None:
            self.estimator = self._build_estimator()

        self.estimator.fit(X, y)
        return self

    def predict(self, X):
        if self.estimator is None:
            raise ValueError("model has not been trained or loaded")
        X = _validate_feature_matrix(X)
        return self.estimator.predict(X).astype(np.float32)

    def save(self, path):
        if self.estimator is None:
            raise ValueError("cannot save an untrained model")
        with open(path, "wb") as model_file:
            pickle.dump(
                {
                    "estimator": self.estimator,
                    "random_state": self.random_state,
                    "forest_kwargs": self.forest_kwargs,
                    "feature_names": self.feature_names,
                },
                model_file,
            )
        return path

    @classmethod
    def load(cls, path):
        with open(path, "rb") as model_file:
            payload = pickle.load(model_file)

        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict) or "estimator" not in payload:
            raise ValueError("model file does not contain a valid CBHModel payload")

        return cls(
            estimator=payload["estimator"],
            random_state=payload.get("random_state", 42),
            feature_names=payload.get("feature_names"),
            **payload.get("forest_kwargs", {}),
        )

    def _build_estimator(self):
        try:
            from sklearn.ensemble import RandomForestRegressor
        except ImportError as exc:
            raise ImportError(
                "scikit-learn is required to train CBHModel. "
                "Install project requirements before training."
            ) from exc

        defaults = {
            "n_estimators": 200,
            "max_depth": None,
            "min_samples_leaf": 2,
            "n_jobs": -1,
            "random_state": self.random_state,
        }
        defaults.update(self.forest_kwargs)
        return RandomForestRegressor(**defaults)


def _validate_feature_matrix(X):
    X = np.asarray(X, dtype=np.float32)
    if X.ndim != 2:
        raise ValueError("X must be a 2D feature matrix")
    if not np.all(np.isfinite(X)):
        raise ValueError("X contains non-finite values")
    return X
