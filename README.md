# ばんえいAI - GitHub Pages版

この版は **Streamlit/Pythonを使わず、HTML/CSS/JavaScriptだけ** で動きます。

## GitHub Pagesで公開する手順

1. このZIPの中身をGitHubリポジトリのルートへアップロード
2. GitHub → **Settings**
3. 左メニュー → **Pages**
4. `Build and deployment` の Source を **Deploy from a branch**
5. Branchを **main / (root)** にして Save
6. 数分待つと `https://<ユーザー名>.github.io/<リポジトリ名>/` で開けます

## 保存について

レース・結果・学習重みは **ブラウザのLocalStorage** に保存します。
そのためStreamlit Cloudのような再起動で消えることはありません。

ただし以下では消える可能性があります。

- Safari/Chromeのサイトデータを削除
- 別端末で開く
- プライベートブラウズを使う

そのため「バックアップ」タブからJSONを定期的に書き出してください。

## ファイル

- `index.html`
- `style.css`
- `app.js`
- `.nojekyll`

