# CLAUDE.md

このファイルはClaude Codeがこのリポジトリで作業する際のガイドです。

## プロジェクト概要

**完全無料・完全自動**で運営する、複数ジャンルの収益サイト(GitHub Pagesでホスティング)。
「リサーチ→執筆→公開→アクセス分析→修正」のルーティンを人手を介さず回すことを目的とした個人プロジェクト。
`rakuten_threads_bot` / `youtube_jido` / `note_auto_bot` と同じ運用者が管理しており、それらのAI生成・スケジューリングの仕組みを流用している。

- **商品紹介・比較記事**: 楽天市場APIの実データ(価格・レビュー・商品説明)だけを根拠にAIが執筆。記事内に楽天アフィリエイトリンクを挿入し、必ず「PR」表記を付ける。
- **情報系記事**: 商品を紹介しない、検索流入・広告収益(将来のGoogleアドセンス)向けのお役立ち記事。
- 1回の実行(`generate_and_publish.py`)で記事を1本だけ生成・公開する。ジャンルは`content_pipeline.py`の`GENRES`でローテーション。

## 主要ファイル

- `content_pipeline.py`: ジャンルローテーション・記事タイプ選択(商品紹介 or 情報系)・楽天データ取得・AI呼び出しの統括(`import claude_writer as ai_writer`で切り替え済み)
- `claude_writer.py`: **記事生成のメイン**。Claude Code CLI(`claude -p`ヘッドレス実行、`CLAUDE_CODE_OAUTH_TOKEN`でサブスク認証)を使う。情報系記事はWebSearchツールを許可し、実際にリサーチしてから執筆させる
- `ai_writer.py`: 旧Gemini API版(未使用のレガシー)。Google検索連携が無料枠で429エラーになる問題があり2026-09-10にclaude_writer.pyへ切り替えた。参考実装として残置
- `rakuten_source.py`: 楽天市場商品検索APIのラッパー(rakuten_threads_botと同じロジック)
- `photo_source.py`: Pexels API(無料)で情報系記事のヒーロー画像を検索・取得
- `thumbnail.py`: ヒーロー画像の用意(`create_hero_image`: 商品記事→実商品写真、情報記事→Pexels写真、どちらも失敗時のみPillowでグラデーション画像を生成)
- `site_builder.py`: Jinja2で`docs/`配下に静的HTML(記事ページ・一覧・sitemap.xml・robots.txt)を生成(GitHub Pagesの「mainブランチ/docsフォルダ」設定にそのまま対応)
- `templates/`: `base.html` / `article.html` / `index.html`(Jinja2テンプレート)
- `generate_and_publish.py`: 上記を1回の実行でまとめて行うエントリーポイント。Gitリポジトリが初期化済みならcommit&pushまで行う
- `posted_articles.json`: 投稿済み記事の履歴(重複防止・使用済み商品ID管理)
- `bot_state.json`: ジャンル/トピックローテーションの現在位置
- `site_log.txt`: 実行ログ
- `docs/`: 生成された静的サイト本体(GitHub Pagesに公開する対象)
- `.env`: APIキー類(絶対にコミットしない)

## 現在のステータス(2026-09-10時点)

- **サイトは実際に公開済み**: https://himapima.github.io/free-content-site/ (GitHubリポジトリ: https://github.com/himapima/free-content-site 、mainブランチ/docsフォルダをGitHub Pagesで配信)。**2026-09-12にGitHubユーザー名を`enupi80-droid`→`tigeregg80`へ変更し、さらに同日中に`tigeregg80`→`himapima`へ再変更した**(旧ユーザー名がユーザーの実メールアドレスのローカル部と一致しており、サイトURLから本人特定につながるリスクがあったため)。`.env`の`SITE_BASE_URL`・`rakuten_threads_bot/main.py`の送客リンク・`comments-worker/wrangler.toml`の`ALLOWED_ORIGIN`・git remote・git commit作者情報を全て新ユーザー名に更新済み。コメント機能のCloudflare Worker(workers.dev)サブドメインはGitHubユーザー名とは別物(Cloudflareアカウント側の設定)のため`tigeregg80.workers.dev`のまま未変更(`docs/comments.js`の`COMMENTS_API_BASE`・`wrangler.toml`の`name`は今回のGitHubユーザー名変更の対象外)。
- Phase 1(記事生成・サイト構築)・Phase 2(GitHub Pagesへの実公開)は実装・検証済み。情報系記事・商品紹介記事とも実データで生成成功を確認。
- **記事生成エンジンはClaude Code CLIに切り替え済み**(`claude_writer.py`)。理由: (1) Geminiの無料枠はGoogle検索連携(grounding)が429エラーで使えず「リサーチせずに書く」状態になっていた、(2) ユーザーから「Geminiじゃなくて、このクロード(サブスク課金分)でやったら」と明示的な指示があった。`claude setup-token`で発行した長期OAuthトークン(`CLAUDE_CODE_OAUTH_TOKEN`、サブスクリプション契約が必要・APIキー従量課金ではない)で認証し、`claude -p`のヘッドレス実行で記事を生成する。情報系記事はWebSearchツールを許可し、実際にリサーチしてから書かせている(重要: [[feedback_research_before_writing]]参照、検索なしでの生成に戻さないこと)。
- Node.js・公式`@anthropic-ai/claude-code`パッケージはポータブル版で`C:\Users\naoya\tools\node\`配下に導入済み(管理者権限のwinget/MSIインストールがUAC待ちでハングしたため、zip版を展開する方式にした)。
- Gemini版(`ai_writer.py`)は未使用のまま残置(参考・将来のフォールバック候補)。GEMINI_API_KEYはこのサイト専用の新規キーに切り替え済みだったが、現在は使っていない。
- 楽天商品名が長い(全角スペース混じりなど)ため、商品紹介記事のH2見出しには商品名をそのまま使わせていない。AIには`sections`の各要素に`product_index`(1始まり、何番目の商品データに対応するか)を出力させ、`content_pipeline._attach_items_to_sections`がそれを使って商品カードを紐付ける(`product_index`が無い場合のみ空白差異を無視した名前一致にフォールバック)。見出しは自然な短文、商品の正式名称は商品カード内に表示する。
- 2026-09-10にデザインを全面刷新(Web検索でリサーチ済み、詳細は`C:\Users\naoya\.claude\skills\free-content-site\SKILL.md`の「デザイン方針」参照)。記事の全内容を`posted_articles.json`に保存するようにしたため、`python site_builder.py`(=`rebuild_all_pages()`)でAI呼び出しなしに全ページへデザイン変更を反映できる。
- ヘッダーにジャンル別ナビゲーション、`docs/categories/<genre_id>.html`のカテゴリー一覧ページ、トップページの注目記事(最新1件の大きなカード)、ファビコン、記事ページのJSON-LD(Article構造化データ)を追加済み。
- **姉妹プロジェクトrakuten_threads_botから送客する仕組みを追加**(2026-09-10、ユーザー提案): Threadsの役立ち情報(Tips)投稿に、同ジャンルのfree_content_site最新記事へのリンクを添えるようにした(`rakuten_threads_bot/main.py`の`get_site_article_link`)。Tips投稿はもともと収益化していないため、送客に使っても既存の商品紹介投稿(Rakutenへの直接リンクが主CTA)と競合しない。
- Phase 5のうち日次タスク`ContentSite_EveningAutoUpdate`(ログオン時トリガー+20時以降+1日1回ガード、`run_if_evening.py`)は登録済み。
- Phase 3(Search Console/Analytics連携によるアクセス分析→自動修正ループ)は**未着手**。Google Cloudでの OAuthクライアント発行・Search Console/Analyticsプロパティ作成というユーザー側の追加作業が必要。記事の蓄積・インデックス登録には数日〜数週間かかるため、急ぐ理由がない限り後回しでよい。
- Google Search Console/Analyticsの「サイト所有権確認」「アクセス解析タグの設置」自体は、ユーザーがプロパティを作成して確認コード/測定IDを教えてくれれば、Claudeが`templates/base.html`にタグを追加するだけで完了する(OAuth連携なしでも可視化はできる)。
- **コメント機能(2026-09-11追加、同日中にgiscusから自作に差し替え)**: 当初はgiscus(GitHub Discussions利用)を`templates/article.html`に埋め込んだが、GitHubアカウントが無い訪問者もコメントできるようにするため、Cloudflare Worker + D1(`comments-worker/`)による匿名コメント機能を自作して差し替えた。`docs/comments.js`が記事ページからWorkerのAPIを呼び出す。管理用の削除トークンは`.env`の`COMMENTS_ADMIN_TOKEN`。
- **ジャンルを5つに拡大(2026-09-12)**: 美容/キッチン/生活雑貨に加え、ガジェット・メンズファッションを追加。各ジャンルの情報系記事ネタ(`info_topics`)も5→8〜10個に増量し、ネタ切れによる重複記事を防止。
- **ジャンルを8つに拡大(2026-09-21、ユーザー依頼)**: 「便利家電・最新家電、アップル最新情報、ファーウェイ最新機器情報のジャンルを増やして」との依頼で`appliance`(便利家電・最新家電/楽天キーワード「時短家電」)・`apple`(Apple最新情報/「iPhoneアクセサリー」)・`china_gadget`(Huawei・中華ガジェット/「スマートウォッチ」)を追加。情報系記事は`claude_writer`がWebSearchで実際に調べてから書くため、「最新○○」系のネタでも執筆時点の情報になる(Apple枠でテスト生成し、iPhone17世代の変更点記事が出ることを確認済み)。1日2本・8ジャンルのローテーションなので、各ジャンルはおおよそ4日に1本のペース。
- **記事0本のジャンルはナビ・サイトマップに出さない(2026-09-21)**: ジャンルを増やした直後は記事が0本で、そのままだと「開いても何も無いカテゴリーページ」がメニューに並んでしまうため、`site_builder._refresh_nav`で記事が1本でもあるジャンルだけに絞るようにした。最初の記事が入った時点で自動的にメニューへ現れる。
- **1日の投稿本数を1→2本に変更(2026-09-12)**: `run_if_evening.py`が`generate_and_publish.py`を2回連続実行するように変更(`rakuten_threads_bot`と同じPOSTS_PER_RUNパターン、間隔120秒)。
- **「このサイトについて」「プライバシーポリシー」ページを追加(2026-09-12)**: `templates/page.html` + `site_builder.render_static_pages()`で生成、フッターにリンクを設置。将来のGoogleアドセンス審査にも必要なページ。
- **gitコミットの作者情報を匿名化(2026-09-12)**: 過去の全コミットが`enupi80-droid <enupi80@gmail.com>`(本名メール)になっていたため、`git filter-branch`で全コミットの作者/コミッターを`tigeregg80 <325646763+tigeregg80@users.noreply.github.com>`(GitHubのnoreplyアドレス)に書き換え、force pushした。以後のコミットもこの`git config`のまま行うこと(絶対に本名メールに戻さない)。書き換え前のバックアップは`C:\Users\naoya\Desktop\free_content_site_backup_before_rewrite.bundle`。**同日中にGitHubユーザー名をさらに`tigeregg80`→`himapima`へ変更したため、`git config user.email`も`325646763+himapima@users.noreply.github.com`に更新済み(数字のユーザーID部分は不変)。**
- **記事ヒーロー画像の重複を修正(2026-09-11)**: `photo_source.fetch_photo`が常にPexels検索の上位1件だけを取得していたため、`photo_query`がジャンル固定(`content_pipeline.py`の`GENRES`)である情報系記事は同ジャンル内で同じ写真になっていた。候補を30件取得し`used_photos.json`(使用済みPexels写真ID)で重複を避けてランダムに選ぶよう修正。既存記事の画像も再生成済み。
- **デザインは外部サイトリサーチ済み(2026-09-11)**: 2026年のブログ/LPデザイン動向を調査した結果、現行デザイン(セリフ+サンセリフ、カード型グリッド、ソフトな box-shadow+ホバーで浮き上がる、余白重視)は「ミニマル・エディトリアル」路線として概ねトレンドに合致していることを確認。今後さらに手を入れるなら、2026年のもう一つの潮流である**Bento UI**(大小の角丸ボックスをパズル状に組み合わせるモジュール型レイアウト)を注目記事セクション等に取り入れる余地がある。デザイン改善は継続タスクとして今後も外部リサーチしながら進める。

## 自動投稿スケジュール

`ContentSite_EveningAutoUpdate`(日次・ログオン時トリガー、20時以降・当日未実行なら`generate_and_publish.py`を1回実行)を登録済み。`ContentSite_WeeklyReview`(週次のアクセス分析→修正)はPhase 3未着手のため未登録。

## ユーザーについて

- **非エンジニア**。コードは自分でほぼ書けないため、実装・修正・運用のほとんどをClaude Codeに任せたい。
- 説明は専門用語を避け、平易な言葉で。「何が起きて」「次に何をすればいいか」を明確に伝える。

## 作業時の判断方針

2026-09-10にユーザーから「全部実装・スキル化・ルーティン化までやって」と明示的に全権委任を受けている。日々の運用判断(ジャンル選定・トピック選定・記事本数など)は都度確認せず実行してよい。

ただし以下は安全ルール上Claudeが代行できないため、都度ユーザーにお願いする:
- GitHubアカウントの新規作成・ログイン(`gh auth login`はブラウザ認可のみなら代行可)
- Googleアカウントでの新規サービス登録・フォーム送信(Search Console/Analyticsのプロパティ作成、Googleアドセンスへの申請)
- 上記に伴うパスワード入力

- `.env`の中身(APIキー・アクセストークン)を出力・ログ表示・コミットしない。特に`CLAUDE_CODE_OAUTH_TOKEN`はサブスクリプションに直結する長期トークンなので厳重に扱う。
- 商品紹介記事は景品表示法のステマ規制対応として、必ず「PR」表記を含める(削除しない)。
- **記事は必ずリサーチしてから書く(重要・繰り返し指摘あり)**: [[feedback_research_before_writing]]参照。情報系記事は`claude_writer.py`でWebSearchツールを必ず使わせること。検索なし(一般知識のみ)での生成に戻さない。
- **Claude Code CLIの利用はサブスクリプション契約が前提**。`CLAUDE_CODE_OAUTH_TOKEN`が失効/未設定だとエラーになる(トークンは`claude setup-token`で再発行、ユーザーの対話操作が必要)。ANTHROPIC_API_KEYによる従量課金には絶対に切り替えないこと(ユーザーから明確に「課金はしない」と念押しされている)。

## 技術メモ

- 必須環境変数: `RAKUTEN_APP_ID`, `RAKUTEN_ACCESS_KEY`, `RAKUTEN_AFFILIATE_ID`, `CLAUDE_CODE_OAUTH_TOKEN`
- 任意環境変数: `SITE_BASE_URL`(公開後のサイトURL。sitemap/canonical生成に使用。未設定の間はsitemapを生成しない)、`SITE_ARTICLE_TYPE_RATIO`(既定0.5、情報系記事になる確率)、`CLAUDE_CLI_PATH`(claude.exeの場所。既定値のままで通常は問題ない)、`PEXELS_API_KEY`(情報系記事のヒーロー画像用)
- ローカルでの動作確認: `python generate_and_publish.py` を実行後、`python -m http.server --directory docs 8765` 等で`docs/`を配信してブラウザ確認できる
- ジャンル・トピックを増やす場合は`content_pipeline.py`の`GENRES`を編集する(`color`と`photo_query`も一緒に設定する)
