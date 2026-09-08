# v0.5 地形改良

## 変更範囲

ユーザーの承認に基づき、コースの左右形状と高さ、およびそれに追従する沿道物・一般車の投影座標を変更します。その後の追加承認に基づき、見た目を保った道路描画の高速化も行います。対象は`camera_shift`・`draw_road`・`gfx_span`に限定し、ハンドル・加減速・接触・遭遇イベント・時計・音の実装は保持します。バージョン表記と出力先はv0.5へ更新します。

v0.4のROMと検証記録を保持しています。比較に必要なソース・資産・ROMは`outputs/baseline-v0.4/`へ固定し、SHA-256で検査します。

## 同じ512KiBの構成

コースは従来どおり1024地点×256バイトです。各地点には道路41本分の帯、沿道物8個分、一般車などの投影16点分を保持します。車や風景の画像を追加して容量を増やす変更ではありません。

カーブによる外向きドリフトは従来の計算のまま、曲率データの強さを±33以内に抑えます。最高速の1フレームで1〜2地点進むため、隣接地点と2地点先、周回の継ぎ目を検査します。

## 描画の安全確認

既存の空画像の読み出しに合わせ、地平線を64〜112の範囲に保ちます。道路と一般車の符号付き8ビット横座標の飽和、路面の欠け、坂での遮蔽、近景の連続性も検査します。完成イメージ図と、実ROMをopenMSXで動かした画像・映像は区別します。

## 最終版の検証結果

最終ROMは524,288バイト、配置済み491,520バイト、空き32,768バイトです。

```text
53cb766fa001831a8ed75e93aee2c7059d61ad24e24d715811e59e5369412191
```

- [総合ネイティブ検証](../outputs/verification-v0.5.json)：83/83合格。リセット後、キー操作だけで全8区間を一周し、平均29.837fps。追い越し4台、接触0回、UFO回避1回、路外0回。時計は表示24.1秒に対し外部計測24.198秒。
- 旧版と同じ12種類の負荷条件をすべて通過。重い区間2は27.268fps、区間5は27.506fps。全区間30fps固定ではありません。追加の時刻・フレーム同時取得でも最重条件27.997fpsを確認しています。
- [変更範囲・地形検査](../outputs/terrain-scope-verification-v0.5.json)：21/21合格。強化した地形、画像資産、操作、イベント、時計の実装を保持。
- [描画計算の同値検査](../outputs/render-equivalence-v0.5.json)：11/11合格。全1024地点×全289ハンドル位置、計295,936状態で最終画素が同じ。ASMの算術・描画順・作業領域7バイト・コンパイル結果も照合。
- [横帯の低レベル描画検査](../outputs/span-equivalence-v0.5.json)：8/8合格。符号付き座標3,015,167ケース、全256色、I/O・スタック15,360ケースを照合。
- [実ROM同士の画素比較](../outputs/native-render-equivalence-v0.5.json)：263/263場面、20,198,400画素で差分0。通常走行・左右端・峠・一般車・UFO・時計・ポーズを含みます。各ROMで描画状態を固定し、3フレームの待機後と次フレームの安定も確認。これは入力だけの一周走行とは別の検査です。
- [再生成ビルド](../outputs/rebuild-verification-v0.5.json)：6/6合格。風景・車・コースの再生成を含め、最終ROMがバイト単位で一致。

高速化では、R800のカメラ計算、41本の道路帯を処理する専用ループ、V9990の帯描画命令の準備を短縮しました。画面全幅の道路に完全に隠れる草地・路肩の描画だけ省略し、最終的な絵は変えていません。比較用の小さなソース・データ集は`outputs/baseline-v0.5-terrain/`に固定しています。

[サンプルGIF](../outputs/v0.5/scenic-drive.gif)は最終ROMの連続210フレーム、約7秒・29.819fpsです。全フレームの画素と再生時間を元のキャプチャへ照合し、UFOなどのハプニングが映らないことも確認しています。[撮影記録](../outputs/v0.5/scenic-capture.json)と[検査結果](../outputs/v0.5/scenic-verification.json)を同梱しています。

検証対象はopenMSX 21.0、Panasonic_FS-A1ST＋gfx9000です。実機は未検証。v0.5の公開には検証済みROM、ソース、走行GIF、最終検証結果を使用し、v0.4のROMと検証記録も保持しています。

機能確認用の静止画49枚とGIFを同梱し、GIF作成用の連番PNGは非同梱です。JSON内の連番PNGパスは検証時の記録で、再撮影時に生成されます。元画像のハッシュ・時刻・状態値と、GIFの画素・再生時間の一致結果を公開しています。

## 地形の検証と高速化前の比較基準

地形のみを変更した候補Aは524,288バイト、配置済み491,520バイト、空き32,768バイトです。高速化前の比較用ソース・コースデータは`outputs/baseline-v0.5-terrain/`に収録しています。試験ROMと全作業履歴は開発側で保持し、公開物には含めていません。

```text
8849a4e19fb97fec44f5276026543079ec0529271141e09be6a33d8f42a58606
```

- 候補Aの地形・変更範囲の検査は19/19合格、再生成ビルドは6/6合格（ROMバイト一致）。この段階のROM差分はコース領域とタイトルの版番号1バイトだけです。
- 候補Aの総合ネイティブ検証は74/76合格。区間2・5のFPSが目標に届かなかったため、描画の高速化を追加しています。コースデータのSHA-256を固定し、迫力を下げる調整は行いません。
- 同じ中景の10本の路面帯で、中心位置の最大の広がりは旧5ピクセルから52ピクセルへ増えています。画面全体や全区間の曲率が一律10倍という意味ではありません。
- 地平線は67〜112、曲率による横流れのメタデータは−33〜33、符号付き横座標の飽和なし。

峠の付近では、手前の丘に隠れた遠い道路が現れるため、同じ走査行が別の地点を指すようになります。最初の全行一律の連続性検査は、この可視領域の切替も不連続として検出しました。実ROMの連続画像を確認し、近景の連続性と遠方の遮蔽切替を別々に検査しています。大きな変化は地平線の近傍だけで、測定された最大46ピクセルという値も検査記録に残しています。近景（y≥122）は1地点進行あたり中心最大2ピクセル・半幅最大9ピクセル、一般車の投影と坂の遮蔽境界も連続しています。

不採用の高速化候補と性能不足の結果も開発側の作業用ディレクトリーに保持しています。途中のテストで起動直後のBIOS画面を撮影してしまった1回は無効として記録し、起動完了を待ってから別の検証記録を作成しました。

v0.4で生じた外部時計比較の許容差超過は、今回の地形変更で修正したとは扱いません。旧チェックの0.25秒の許容値も維持します。今回の専用検証器はHTTP接続を再利用し、無効な画面や通信障害があれば結果を合格にせず停止します。

## 実ROM同士の比較の再現

通常のビルド・検証はREADMEの手順を使います。高速化前の候補Aも比較する場合は、現在の資産・共通コードに同梱の比較用ソースを重ね、別の作業フォルダーでビルドします。リポジトリー直下のPowerShellで、SDCC/Pasmoの設定後に実行してください。

```powershell
$comparisonBuild = Join-Path (Get-Location) "work/native-compare-A"
if (Test-Path -LiteralPath $comparisonBuild) { throw "比較先は新しいフォルダーを指定してください。" }
New-Item -ItemType Directory -Path "$comparisonBuild/tools" | Out-Null
Copy-Item -LiteralPath src,assets -Destination $comparisonBuild -Recurse
Copy-Item -LiteralPath tools/build.py -Destination "$comparisonBuild/tools/build.py"
Copy-Item -Path outputs/baseline-v0.5-terrain/src/* -Destination "$comparisonBuild/src"
Copy-Item -LiteralPath outputs/baseline-v0.5-terrain/assets/course.bin -Destination "$comparisonBuild/assets/course.bin"
python "$comparisonBuild/tools/build.py" --pack-only
Get-FileHash "$comparisonBuild/outputs/MAGICAL_HAPPY_RALLY-v0.5.rom"
```

AのSHA-256が上記の`8849a4e1…`と完全一致することを確認してください。A用の別ターミナルでは`OPENMSX_PORT=18799`を設定し、`node tools/emulator_host.mjs -cart work/native-compare-A/outputs/MAGICAL_HAPPY_RALLY-v0.5.rom -romtype ASCII8`で起動します。最終版はREADMEの手順で18798へ起動します。両方ともタイトル画面が表示されてから、次を実行します。

```text
python tools/compare_render_native.py capture --source-root work/native-compare-A --port 18799 --out work/native-pixels-A
python tools/compare_render_native.py capture --port 18798 --out work/native-pixels-final
python tools/compare_render_native.py compare --reference work/native-pixels-A --candidate work/native-pixels-final --out work/native-pixel-comparison.json
```

出力先が存在する場合は新しい名前を指定してください。検証は対象ROMのハッシュとネイティブのロード状態を確認し、不一致や未完了があれば停止します。終了後はそれぞれの起動ターミナルでCtrl+Cを押し、再ビルドの前にROMのロックを解除してください。
