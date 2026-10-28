"""字符 TF-IDF 检索；来源 ID 始终对应完整政策 chunk。"""

import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from aftersales.models import Policy


def normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


@dataclass(frozen=True)
class Hit:
    policy: Policy
    score: float
    matched_field: str


class PolicyRetriever:
    def __init__(self, policies: tuple[Policy, ...]):
        self.policies = policies
        self.vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 4), preprocessor=normalize
        )
        # Multiple field representations belong to one logical chunk and one source ID.
        # Max cosine is an actual measured similarity, never a score assigned by intent.
        documents = []
        self.fields = []
        for index, policy in enumerate(policies):
            views = [("title", policy.title), ("content", policy.content)]
            views += [(f"alias:{i}", alias) for i, alias in enumerate(policy.retrieval_aliases)]
            views += [
                (
                    "full",
                    " ".join(
                        (
                            policy.title,
                            policy.content,
                            policy.applicability,
                            *policy.retrieval_aliases,
                        )
                    ),
                )
            ]
            for name, text in views:
                documents.append(text)
                self.fields.append((index, name))
        self.matrix = self.vectorizer.fit_transform(documents)

    def search(self, query: str, limit: int = 3) -> tuple[Hit, ...]:
        vector = self.vectorizer.transform([query])
        scores = cosine_similarity(vector, self.matrix)[0]
        best = {}
        for (index, name), score in zip(self.fields, scores, strict=True):
            if index not in best or score > best[index].score:
                # Only remove floating point roundoff outside the mathematical [0, 1] range.
                best[index] = Hit(self.policies[index], min(1.0, max(0.0, float(score))), name)
        ranked = sorted(best.values(), key=lambda hit: (-hit.score, hit.policy.id))
        return tuple(ranked[:limit])
