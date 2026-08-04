# ばんえいAI 完成版

ばんえい競馬専用の予想・保存・結果入力・自動回顧・自動学習ツールです。

## 追加機能
- 2日24Rの検証を反映した初期重み
- 障害力 / 障害安定 / 馬場水分適性 / 斤量適性 / 近走を分離評価
- 穴スコア
- 3連単 / 3連複候補
- 成績ダッシュボード
- CSV一括入力
- バックアップ / 復元

## Streamlit Cloud
Main file path は `app.py`。

## ローカル起動
```bash
pip install -r requirements.txt
streamlit run app.py
```
