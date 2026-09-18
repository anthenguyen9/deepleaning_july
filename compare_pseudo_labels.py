"""Compare ViTASA baseline with AI-assisted Google review training data.

Run from the repository root with: python compare_pseudo_labels.py
Never treat data/gold/dev.json or data/gold/test.json as independent human truth.
"""
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from pipeline import CLASSES, metrics, normalize, read


def target(rows):
    return np.asarray([[int(label in row["labels"]) for label in CLASSES] for row in rows])


def fit_predict(x_train, y_train, weights, x_eval):
    predictions = []
    for col in range(y_train.shape[1]):
        if len(np.unique(y_train[:, col])) == 1:
            predictions.append(np.full(x_eval.shape[0], y_train[0, col]))
            continue
        model = LinearSVC(C=1, class_weight="balanced", random_state=42, max_iter=5000)
        model.fit(x_train, y_train[:, col], sample_weight=weights)
        predictions.append(model.predict(x_eval))
    return np.asarray(predictions).T


vitasa = {s: read(Path("data") / f"{s}.json") for s in ("train", "dev", "test")}
pseudo = read(Path("data/gold/train.json"))
ai_records = json.loads(Path("data/annotation_ai_20260917.json").read_text(encoding="utf-8"))["records"]
ai_by_id = {r["restaurant_id"] + ":" + r["review_id"]: sorted(set(r["labels"])) for r in ai_records}
ai_matched = sum(r["id"] in ai_by_id and r["labels"] == ai_by_id[r["id"]] for r in pseudo)
held_out = {normalize(r["text"]).casefold() for s in ("dev", "test") for r in vitasa[s]}
train_texts = {normalize(r["text"]).casefold() for r in vitasa["train"]}
pseudo_clean = []
seen = set()
for row in pseudo:
    key = normalize(row["text"]).casefold()
    if key not in held_out and key not in train_texts and key not in seen:
        pseudo_clean.append(row)
        seen.add(key)

report = {
    "evaluation": "ViTASA human span-derived labels; fixed train/dev/test split",
    "pseudo_source": "AI-assisted labels from data/gold/train.json; not independently validated gold",
    "pseudo_original": len(pseudo),
    "pseudo_labels_matching_ai_export": ai_matched,
    "pseudo_accepted": len(pseudo_clean),
    "pseudo_excluded_overlap_or_duplicate": len(pseudo) - len(pseudo_clean),
    "config": "char TF-IDF 3-5, min_df=2, max_features=60000, LinearSVC C=1, balanced",
}

def score(rows, predictions):
    result = metrics(target(rows), predictions)
    return {k: result[k] for k in ("pair_micro_f1", "pair_macro_f1_15_labels", "acd_macro_f1", "exact_match")}

vectorizer = TfidfVectorizer(
    analyzer="char", ngram_range=(3, 5), min_df=2,
    max_features=60000, sublinear_tf=True,
)
x_train = vectorizer.fit_transform([r["text"] for r in vitasa["train"]])
y_train = target(vitasa["train"])
x_dev = vectorizer.transform([r["text"] for r in vitasa["dev"]])
x_test = vectorizer.transform([r["text"] for r in vitasa["test"]])
base_dev = fit_predict(x_train, y_train, np.ones(len(y_train)), x_dev)
base_test = fit_predict(x_train, y_train, np.ones(len(y_train)), x_test)
report["baseline"] = {"dev": score(vitasa["dev"], base_dev), "test": score(vitasa["test"], base_test)}

combined_rows = vitasa["train"] + pseudo_clean
vectorizer = TfidfVectorizer(
    analyzer="char", ngram_range=(3, 5), min_df=2,
    max_features=60000, sublinear_tf=True,
)
x_combined = vectorizer.fit_transform([r["text"] for r in combined_rows])
y_combined = target(combined_rows)
x_dev = vectorizer.transform([r["text"] for r in vitasa["dev"]])
x_test = vectorizer.transform([r["text"] for r in vitasa["test"]])
report["candidates_dev"] = {}
best = None
for pseudo_weight in (0.25, 0.5, 1.0):
    weights = np.r_[np.ones(len(vitasa["train"])), np.full(len(pseudo_clean), pseudo_weight)]
    pred = fit_predict(x_combined, y_combined, weights, x_dev)
    scores = score(vitasa["dev"], pred)
    report["candidates_dev"][str(pseudo_weight)] = scores
    if best is None or scores["pair_micro_f1"] > best[1]:
        best = (pseudo_weight, scores["pair_micro_f1"])

report["selected_pseudo_weight"] = best[0]
weights = np.r_[np.ones(len(vitasa["train"])), np.full(len(pseudo_clean), best[0])]
report["augmented_test"] = score(vitasa["test"], fit_predict(x_combined, y_combined, weights, x_test))
Path("outputs/gold_aug_experiment.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
