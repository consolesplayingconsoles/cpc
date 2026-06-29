# Boku Doraemon — open verification flags (traceable index)

Non-blocking questions parked for later. **None of these affect the translation** — every line
is committed and playable; this is just where we track names/wording we'd like a real source to
confirm. Sources that count: the dub corpus (`sandbox/.../dub-subs/`, grep), the operator's
lived memory of the classic TV3 dub, or a found episode. **An LLM "confirming" is not a source.**

Working scratch with full context lives at `sandbox/gemini-flags.md` (gitignored). This file is
the durable, shareable summary. Offsets are into `STORY.PAC` (find them in the project state.json).

How a flag resolves: (a) operator recognizes it from the classic dub → adopt instantly; (b) a
line/scene reminds us of a specific episode in the 201-list → grep that episode's subtitle for the
real wording; (c) otherwise the coin stands as a reasonable editorial choice.

---

## A. Gadget coins — corpus-silent (0 dub-corpus hits; not in our 201-ep set)

Real franchise gadgets, but our revival corpus never names them and Gemini's "sources" were
fabricated (see scratch). Coins are reasonable; swap on real confirmation.

> **Process correction + grep sweep (2026-06-28):** all 90 coins were finally run against the local
> corpus — first by full name, then by **partial roots / synonyms of the gadget's function**
> (`grep -F`, fixed strings, so accents/`·`/apostrophes don't trip regex). Every hit was then
> **context-read** to confirm it names the gadget (not an incidental word). **8 turned out to be real
> dub canon** and are promoted to `boku-doraemon-names.md`:
>
> | # | JP | now (canon) | was (my coin) | proof |
> |---|---|---|---|---|
> | 41 | ひらりマント | Capa esquivadora | (same) | "Faré servir la capa esquivadora" ×6 |
> | 51 | 空気ピストル | Pistola d'aire | (same) | "Pistola d'aire!" ×2 (≠ 空気砲 *canó d'aire*) |
> | 23 | まあまあ棒 | Bastó tranquil·litzador | (same) | "El bastó tranquil·litzador!" ×2 |
> | 55 | ねがい星 | **Estrella** dels desitjos | Estel dels desitjos | "Doraemon! L'estrella dels desitjos!" |
> | 39 | 進化退化放射線源 | Raig de l'evolució | Font de radiació evolutiva | "El raig de l'evolució!" |
> | 25 | うらしまキャンディー | **Caramels** d'Urashima | Caramel d'Urashima | "Caramels d'Urashimaaa!" |
> | 36 | 精霊よびだしうでわ | Braçalet **per invocar** esperits | Braçalet invoca-esperits | "El braçalet per invocar esperits!" |
> | 10 | 人間ラジコン | Control remot per humans | Teledirigit humà | "El control remot per humans!" |
> | 83 | ケッシンコンクリート | Ciment de la determinació | Formigó de la decisió | "El ciment de la determinació!" ×2 |
> | 26 | うらめしドロップ | Caramels fantasma | Caramel del rancor | "Els caramels fantasma" ×2 + synopsis |
>
> #83/#26 came from also mining `sandbox/.../episode-synopses.txt` (the official 3cat `entradeta`/
> `descripcio` per-episode gadget descriptions — cleaner than subtitles, still broadcast-sourced).
> **10 total** confirmed/corrected, all patched in state.json. **Lesson: grep BEFORE flagging.** Hits that were context-rejected (NOT
> adopted, stay coins): #18 クローンリキッド vs "elixir duplicador" (= a different gadget, バイバイン
> the object-doubler); #11 vs "hipnotitzar objectes" (line *denies* it); #43 "mall" (substring noise).
> Cross-checks the three other LLMs offered (Banda animadora, Formigó de la decisió, Mongeta màgica,
> Gorra de pedra, Placa de mestre superior, Espasa Llampec, "aparells per ser un ninja", Medecina del
> rancor…) **all = 0 in our corpus** → not adopted; an LLM claim + a fan-wiki edit ≠ broadcast
> confirmation. The ~80 still below are genuinely 0-hit; operator memory or a found episode overrides.
> Sweep continues, most-likely gadgets first. (Promoted rows kept in the tables for traceability.)

| # | JP gadget | function | current coin | offset |
|---|---|---|---|---|
| 1 | 室内旅行機 | travel the world without leaving your room | Simulador de viatges | 0x0DB9B6 |
| 2 | ナワバリエキス | essence that marks your own territory | Essència de territori | 0x0E4AE8 |
| 3 | チョージャワラシベ | warashibe lucky-straw → trade up to fortune | Palla de la fortuna | 0x0E928E |
| 4 | へんしんドリンク | drink → transform into any animal | Beguda transformadora | 0x0E92D0 |
| 5 | エスパーぼうし | hat: telekinesis / clairvoyance / teleport (no telepathy) | Barret paranormal | 0x0EDA44 |
| 6 | ミチビキエンゼル | hand-worn angel that tells you what to do | Àngel guia | 0x0EDA82 |
| 7 | こけおどし手投げ弾 | "bluff" grenade — big noise+light, harmless | Granada espantall | 0x0F245C |
| 8 | オートマチック花火 | place it, it launches fireworks by itself | Focs artificials automàtics | 0x0F2494 |
| 9 | 小型潜水艦 | mini submarine, jumps water-to-water | Submarí en miniatura | 0x0F6A1E |
| 10 | 人間ラジコン | radio-control a person | Teledirigit humà | 0x0F6A4E |
| 11 | 無生物さいみんメガフォン | makes an object believe it's something else | Megàfon hipnotitzador d'objectes | 0x0F6A8A |
| 12 | モグラハンド | dig through ground freely | Mà de talp | 0x0FB562 |
| 13 | 地底探検車 | underground digging vehicle | Vehicle subterrani | 0x0FB594 |
| 14 | 宝さがし機 | detects buried treasure | Detector de tresors | 0x0FB5C4 |
| 15 | おせじ口べに／悪口べに | flattery + insult lipsticks | Barres de llavis d'afalac i d'insult | 0x100288 |
| 16 | 山びこ山 | plays back a pre-recorded voice | Muntanya de l'eco | 0x104978 |
| 17 | ムード盛り上げ楽団 | plays music to lift the mood | Banda animadora | 0x1049B0 |
| 18 | クローンリキッドごくう | a pulled hair becomes your double | Líquid clonador | 0x1049E8 |
| 19 | 災難予報機 | forecasts coming disasters | Predictor de desgràcies | 0x1093A8 |
| 20 | いいとこ選択肢ボード | change your own abilities | Tauler de qualitats | 0x109412 |
| 21 | はいりこみかがみ | enter the world reflected in the mirror | Mirall transitable | 0x10DA92 |
| 22 | うそつ機 | any lie you tell is believed | Màquina de mentir | 0x1124EE |
| 23 | まあまあ棒 | calms anger (say "va, calma") | Bastó tranquil·litzador | 0x112526 |
| 24 | さいみんグラス | hypnotise whoever you look at | Ulleres hipnotitzadores | 0x112556 |
| 25 | うらしまキャンディー | kindness returns to you multiplied | Caramel d'Urashima | 0x117218 |
| 26 | うらめしドロップ | drink+sleep → become a vengeful ghost | Caramel del rancor | 0x117252 |
| 27 | かんにんぶくろ | "patience bag" (idiom) | Sac de la paciència | 0x117292 |
| 28 | 壁紙ハウス | wallpaper that turns a spot into a drawn house | Casa de paper de paret | 0x11BA1C |
| 29 | 光ごけ | glowing moss | Molsa lluminosa | 0x11BA4C |
| 30 | ポラロイドミニチュア製造カメラ | photo → makes a miniature | Càmera de miniatures Polaroid | 0x11BA82 |
| 31 | おかし牧草 | feed it to sweets, they multiply | Pastura de llaminadures | 0x11FFE6 |
| 32 | 逆時計 | reverses the flow of time | Rellotge invers | 0x120016 |
| 33 | タイム手袋とタイムめがね | touch/appreciate past or future things | Guants i ulleres del temps | 0x120042 |
| 34 | 断層ビジョン | see a hill's cross-section | Visor d'estrats | 0x124B2A |
| 35 | マグマ探知機 | detects underground magma | Detector de magma | 0x124B5C |
| 36 | 精霊よびだしうでわ | rub it, summon spirits | Braçalet invoca-esperits | 0x124B98 |
| 37 | サンタメール | postcard to Santa | Carta a Santa | 0x129906 |
| 38 | 虫よせボード | board that gathers bugs | Tauler atrau-insectes | 0x129942 |
| 39 | 進化退化放射線源 | evolve/devolve a creature | Font de radiació evolutiva | 0x12997E |
| 40 | 名刀電光丸 | sword with radar, auto-wins | Espasa Llampec | 0x12E236 |
| 41 | ひらりマント | wave it, opponent dodges past | Capa esquivadora | 0x12E286 |
| 42 | コーモンじょう | drink it, everyone bows to you | Poció de l'autoritat | 0x12E2D8 |
| 43 | トンカチ | hammer (for breaking) | Martell demolidor | 0x132A14 |
| 44 | 設計紙 | design paper | Paper de disseny | 0x132A4C |
| 45 | 念画紙 | concentrate → the drawing appears | Paper mental | 0x132A82 |
| 46 | 詰め合わせオバケ | box of ghosts to scare with | Capsa de fantasmes assortits | 0x13730C |
| 47 | 時限バカ弾 | timed → target does something stupid | Bomba d'estupidesa temporitzada | 0x13735E |
| 48 | 空間ひんまげテープ | twist on a handle, no one can enter | Cinta torçaespais | 0x1373AE |
| 49 | 氷ざいくごて | sculpt ice freely | Soldador per esculpir gel | 0x13BA3E |
| 50 | おざしきつりぼり | indoor fishing pond | Estany de pesca de saló | 0x13BAB8 |
| 51 | 空気ピストル | air pistol | Pistola d'aire | 0x1401BC |
| 52 | 透視スクリーン | see the surface from underground | Pantalla de visió travessant | 0x1401EE |
| 53 | みちび機 | gives an omikuji for your worry | Màquina d'auguris | 0x1448D6 |
| 54 | シャーロック・ホームズセット | solves any case | Equip de Sherlock Holmes | 0x14490E |
| 55 | ねがい星 | grants any wish | Estel dels desitjos | 0x14495A |
| 56 | タヌ機 | fool/bewitch someone | Aparell ensarronador | 0x1491E2 |
| 57 | そっくりクレヨン | drawn thing becomes real-identical | Llapis de cera clavat | 0x149218 |
| 58 | ジャストホンネ | makes you speak your true feelings | Poció de la sinceritat | 0x14D9D0 |

Dug 2026-06-27: chased themes to candidate episodes — "En Nobita milionari" = different gadget
(raspall antifricció), "Cultivem focs artificials" = grow-from-seeds, not the auto-fireworks. So
the corpus genuinely lacks all eight. Rejected Gemini's "Essència d'atracció" (wrong meaning).

## A.2 Story-mode gadget coins (2026-06-28 file-order sweep)

Coined while finishing the lower-offset story scenarios (the calendar/cutscene region, offsets
0x07–0x0C). Same status as table A: real franchise gadgets, corpus-silent in our 201-ep set,
reasonable house-style coins, swap on a real dub confirmation. Offsets into `STORY.PAC`.

| JP gadget | function | current coin | offset |
|---|---|---|---|
| アクションクイズ | future quiz-game machine: act out the answer or get zapped | Concurs d'acció | 0x083974 |
| 宇宙完全大百科端末機 | future encyclopedia with an answer to everything | Terminal de la gran enciclopèdia de l'univers | 0x084188 |
| いいわ毛 | head-clip that makes good excuses when you fail | Pèl de les excuses | 0x0844B2 |
| 思いきりハサミ | scissors whose snip cuts off your hesitation | Tisores decididores | 0x078EC2 |
| 兄弟シール | two stickers → the wearers become siblings | Adhesiu de germans | 0x07D5AE |
| 連想式すいり虫メガネ | loose word-association → arrives at the truth | Lupa de deducció per associació | 0x089912 |
| 自動はんばいタイムマシン | vending machine: buy old goods at old prices | Màquina del temps expenedora | 0x08DDE6 |
| ガッチリグローブ | pro glove, any klutz shines (Major-Leaguer set) | Guant infal·lible | 0x08E0D0 |
| ジャック豆 | Jack-and-the-Beanstalk beans, grow to the sky | Mongetes d'en Jack | 0x09997C |
| レコード製造機 | sing → it presses a record (+ sleeve) | Màquina de fer discos | 0x093970 |
| コンチュー丹 | insect powers (butterfly/bee/ant/beetle); slow onset | Píndola insecte | 0x093F66 |
| 石ころぼうし | wear it → everyone ignores you like a pebble | Barret de la pedra | 0x094E30 |
| 忘れ物おくりとどけ機 | sends anything anywhere | Màquina d'enviar oblits | 0x09D77E |
| 空とぶ切手 | stamp → delivers what it's stuck to | Segell volador | 0x09E3BA |
| 入れかえロープ | both ends held → the two swap bodies | Corda d'intercanvi | 0x0A28C4 |
| ジキルハイド | 10-min personality reversal (timid↔bold) | Poció Jekyll i Hyde | 0x0A2D76 |
| ころばし屋 | coin-op box that trips a named foe 3× (pun on 殺し屋) | Ensopegador a sou | 0x0A30EC |
| いつでも日記 | writes your diary by itself — even the future | Diari de qualsevol dia | 0x0AC05E |
| もはん手紙ペン | turns your bad prose into proper sentences | Bolígraf de cartes model | 0x0ACB80 |
| 空気クレヨン | draw in midair | Llapis de cera d'aire | 0x0ACF6A |
| 家元かんばん | signboard → instantly grandmaster of anything | Rètol de gran mestre | 0x0B12EE |
| 招待錠 | half a tablet here + half to a guest → they must come | Poció d'invitació | 0x0B1C84 |
| ハジメテン | everything moves you as if it's your first time | Píndola de la primera vegada | 0x0B1EA8 |
| 正かくグラフ | turns vague rankings into an exact graph | Gràfic exacte | 0x0B6736 |
| ケッシンコンクリート | drink → you see any resolve through to the end | Formigó de la decisió | 0x0B6F3E |
| いないいないシャワー | bends light → you appear as a dodgeable mirage | Dutxa del cucut | 0x0BB1CA |
| クリーニングシャワー | washes off the mirage-shower effect | Dutxa netejadora | (dialogue, 0x0BB79A) |
| ニンニン修行セット | train with it → become ninja-like | Equip d'entrenament ninja | 0x0BBA2E |
| フリダシにもどる | rewind to just before you blurted something | Torna a la casella de sortida | 0x0C0EE6 |
| ハリせんぼんバッジ | badge growls at a lie → liar must make it true | Xapa del peix globus | 0x0C52DE |
| ゲラゲライヤホン | earphones that make you laugh uncontrollably | Auriculars de la riallada | 0x0C5840 |
| 怪談ランプ | tell a ghost story → the tale literally happens | Llàntia de terror | 0x0C98D4 |

Notes: ねがい星 (`Estel dels desitjos`, 0x09E0BC here) and いいとこ選択肢ボード (`Tauler de qualitats`,
0x0B6B48) recur from table A — same coins kept. ジキルハイド and ハリせんぼん lean on a recognised
reference (Stevenson / the puffer-fish "harisenbon"); kept literal-ish so the gag survives. ころばし屋
preserves the koroshiya/korobashiya mishear: Nobita reacts "un assassí a sou?!" (`殺し屋`).

## A.3 The Catalan Fandom wiki is NOT broadcast canon (proven 2026-06-28)

Tried the source the other LLMs cited: `doraemon.fandom.com/ca` *Llista d'aparells de Doraemon*
(real page; direct fetch 403s but the `api.php?action=parse&prop=wikitext` endpoint works). It lists
Catalan gadget names — BUT it is fan-edited (CC-BY-SA), **not** a transcript of the TV3 broadcast, and
it demonstrably diverges from the dub. **Smoking gun:** the wiki calls 通り抜けフープ *"Cercle de pas"*
(0 corpus hits) while the actual broadcast says **cèrcol-passadís** (16 episodes). Every wiki name we
checked = **0 in our corpus** (Banda animadora, Formigó de la decisió, Pomada guanyadora, Poció
transformadora, Placa de mestre superior, Caramels fantasmagòrics, Submarí subterrani, Medecina del
rancor, Cercle de pas). **Conclusion: do not adopt wiki names as canon.** Only the broadcast corpus
(grep) and operator lived-memory are canon. Mild note: the wiki independently produced "Banda animadora"
(#17) and "Formigó de la decisió" (#83) identical to my coins — corroborates the literal coin is
*reasonable*, not that it's *aired*. Those two stay flagged coins, not promoted.

Manga route (for operator to verify by hand): JP per-gadget debut + tankōbon volume IS reliably findable
(JP Wikipedia / pixiv / coocan). Proven: 石ころぼうし (#70) = debut 「だれにも気にされない」(Shōgaku
Rokunensei, Apr 1973), collected in **Tentōmushi Comics Doraemon vol. 4** as 「石ころぼうし」. Caveat: a
manga edition's names may still differ from the TV3 dub, which is what players carry.

## B. Dialogue / name / register flags (open)

| topic | current | offset(s) | question |
|---|---|---|---|
| Pero — Shizuka's dog | kept "Pero" | ~0x05D9AC | did the TV3 dub keep the name or localise it? |
| はねつき (battledore) | "el joc de les pales" | ~0x04E392 | dub's term for the New Year game? |
| あやとり (cat's cradle) | "el joc del fil" | 0x0B1516 | dub's term for the string-figure game? |
| Sewashi addressing Nobita (おじいさん) | "iaio" | 0x0CE8A4+ | does the dub use "iaio" / "rebesavi" here? |
| Geganteta scare line (首つり) | "Un penjat! Ga ha ha!" | 0x0CF02E | confirm speaker = Geganteta (not Gegant) + register |

## C. Confirmed canon (resolved — kept here for reference, not open)

porta màgica · casquet volador · màquina del temps · mocador del temps · mirall multiplicador ·
kit per buscar el tresor (ep 5872688) · túnel de Gulliver · cèrcol-passadís · càmera per
canviar-se · gelatina traductora · canó d'aire · **pastisset de melmelada** (classic-dub /
operator memory). Names canon: Doraemon, Nobita, Shizuka, Gegant, Geganteta, Suneo, Sewashi,
Tamako, Nobisuke, Dorami, Dekisugi, Àvia.
