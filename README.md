# train-data — apne model ka training data (v1)

Supreme Court ke faisle (input) -> court ka khud likha headnote (target). 23,954 jode,
test ke liye 1,000 alag (seed 13). Srot: AWS Open Data `indian-supreme-court-judgments`, CC-BY-4.0.
Banane ka code: `scripts/build_train_data.py` (main branch).

Jodna: `cat train.jsonl.gz.part-* > train.jsonl.gz && sha256sum -c SHA256SUMS`
