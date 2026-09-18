"""Compare ViTASA baseline with AI-assisted or star-rule Google review training data.

Run from the repository root with: python src/compare_pseudo_labels.py --label-policy rating
Never treat data/gold/dev.json or data/gold/test.json as independent human truth.
"""
import argparse
import hashlib
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


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--label-policy", choices=("ai", "rating"), default="ai")
args = parser.parse_args()
vitasa = {s: read(Path("data") / f"{s}.json") for s in ("train", "dev", "test")}
gold = {s: read(Path("data/gold") / f"{s}.json") for s in ("train", "dev", "test")}
pseudo = gold["train"]
ai_records = json.loads(Path("data/annotation_ai_20260917.json").read_text(encoding="utf-8"))["records"]
ai_by_id = {r["restaurant_id"] + ":" + r["review_id"]: sorted(set(r["labels"])) for r in ai_records}
ai_matched = sum(r["id"] in ai_by_id and r["labels"] == ai_by_id[r["id"]] for r in pseudo)
changed_by_star = None
if args.label_policy == "rating":
    source_path = Path("data/annotation_20260917.json")
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))["records"]
    ratings = {r["restaurant_id"] + ":" + r["review_id"]: r["rating"] for r in source}
    destination = Path("data/rating_weak")
    destination.mkdir(parents=True, exist_ok=True)
    weak = {}
    for split, rows in gold.items():
        weak[split] = []
        for row in rows:
            rating = ratings.get(row["id"])
            if rating not in (1, 2, 3, 4, 5):
                raise ValueError(f"Missing or unsupported star rating for {row['id']}: {rating}")
            polarity = "NEGATIVE" if rating <= 2 else "NEUTRAL" if rating == 3 else "POSITIVE"
            aspects = {label.split(":")[0] for label in row["labels"]}
            weak[split].append({
                **row, "rating": rating,
                "labels": sorted(f"{aspect}:{polarity}" for aspect in aspects),
                "label_source": "star_rule_weak",
            })
        (destination / f"{split}.json").write_text(
            json.dumps(weak[split], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    manifest = {
        "source": "data/gold + data/annotation_20260917.json ratings",
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "policy": "1-2 stars NEGATIVE; 3 NEUTRAL; 4-5 POSITIVE; preserve AI-derived aspect presence",
        "warning": "Weak labels, not independent human gold; do not evaluate against this test split as ground truth.",
        "counts": {split: len(rows) for split, rows in weak.items()},
        "changed_label_sets": {
            split: sum(old["labels"] != new["labels"] for old, new in zip(gold[split], weak[split]))
            for split in gold
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pseudo = weak["train"]
    changed_by_star = manifest["changed_label_sets"]
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
    "pseudo_source": (
        "Star rating weak polarity + AI-derived aspect presence from data/gold/train.json"
        if args.label_policy == "rating" else
        "AI-assisted labels from data/gold/train.json; not independently validated gold"
    ),
    "label_policy": args.label_policy,
    "pseudo_original": len(pseudo),
    "pseudo_labels_matching_ai_export": ai_matched,
    "pseudo_accepted": len(pseudo_clean),
    "pseudo_excluded_overlap_or_duplicate": len(pseudo) - len(pseudo_clean),
    "config": "char TF-IDF 3-5, min_df=2, max_features=60000, LinearSVC C=1, balanced",
}
if changed_by_star is not None:
    report["changed_label_sets_by_star_rule"] = changed_by_star
    report["star_rule"] = "1-2 NEGATIVE; 3 NEUTRAL; 4-5 POSITIVE; aspect presence unchanged"

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
report["dev_model_choice"] = (
    f"augmented_weight_{best[0]}"
    if best[1] > report["baseline"]["dev"]["pair_micro_f1"]
    else "baseline"
)
report["selection_rule"] = "Choose by ViTASA dev pair micro-F1; keep baseline on a tie"
weights = np.r_[np.ones(len(vitasa["train"])), np.full(len(pseudo_clean), best[0])]
report["augmented_test"] = score(vitasa["test"], fit_predict(x_combined, y_combined, weights, x_test))
output = Path("outputs/rating_weak_experiment.json" if args.label_policy == "rating"
              else "outputs/gold_aug_experiment.json")
output.write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
