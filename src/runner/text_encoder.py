from typing import Iterable, List, Union

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer


class SentenceTransformerCompat:
    def __init__(self, model_name: str, device: str = "cpu", cache_folder: str = "") -> None:
        self.model_name = model_name
        self.device = device
        self.cache_folder = cache_folder
        self._vectorizer = HashingVectorizer(n_features=768, alternate_sign=False, norm="l2")

    def encode(
        self,
        texts: Union[str, List[str]],
        convert_to_tensor: bool = False,
        show_progress_bar: bool = False,
        device: str = "",
    ) -> np.ndarray:
        if isinstance(texts, str):
            vectors = self._vectorizer.transform([texts]).toarray().astype(np.float32)
            return vectors[0]
        vectors = self._vectorizer.transform(texts).toarray().astype(np.float32)
        return vectors


def get_text_encoder(model_name: str, device: str = "cpu", cache_folder: str = ""):
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        return SentenceTransformer(model_name, device=device, cache_folder=cache_folder or None)
    except Exception:
        return SentenceTransformerCompat(model_name, device=device, cache_folder=cache_folder)
