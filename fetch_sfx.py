"""Download a CC0 sound-effects library for the village cartoon and build sfx/catalogue.json.

  python fetch_sfx.py              download everything missing, then rebuild the catalogue
  python fetch_sfx.py --catalogue  only rebuild sfx/catalogue.json from what is on disk

Sources (all CC0 = public domain dedication, usable in monetised videos, no attribution needed):
  * Kenney audio packs (kenney.nl) - the zip link carries a changing hash, so it is scraped from each pack page at run time.
  * A curated list of Freesound sounds. Every one was checked by hand to be CC0, and the script re-checks the licence on
    the sound's public page before downloading; anything that is not CC0 any more is skipped. Freesound only lets
    logged-in users download originals, so we fetch the public HQ preview (MP3 ~128 kbps), which is plenty for TV mixes.
Stdlib only. Idempotent: existing files are skipped. Run from the repo folder (never from %TEMP%)."""
import io, json, os, re, sys, time, zipfile, urllib.request, urllib.error, html, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.join(HERE, "sfx")
UA = {"User-Agent": "Mozilla/5.0 (toon-render-lab fetch_sfx)"}
CC0 = "CC0 1.0 (https://creativecommons.org/publicdomain/zero/1.0/)"

KENNEY = ["impact-sounds", "interface-sounds", "digital-audio", "casino-audio", "rpg-audio", "ui-audio",
          "sci-fi-sounds", "voiceover-pack", "music-jingles"]   # (voiceover-pack-fighter left out: "kill him" lines, not for kids)

# need, freesound id, uploader, short title  (all verified CC0 on 2026-10-02)
FREESOUND = [
    ("boing", 731261, "sdroliasnick", "cartoon-sound-double-boing"), ("boing", 277291, "TinTinOko", "boing1"),
    ("boing", 186598, "SimbertoB", "Boing"),
    ("slip", 711794, "A_kn", "Awawawaw - cartoon-like slip vocal sfx"), ("slip", 495646, "LilMati", "Retro, Slipping"),
    ("splash", 714669, "alexisrivera3d", "Water Splash"), ("splash", 189499, "VacekH", "water splash 2"),
    ("splash", 524524, "vero.marengere", "Water Splash in Lake 05"),
    ("bucket_clank", 641245, "CaptainYulef", "metal-bucket"), ("bucket_clank", 528494, "martian", "metal bucket hit reverb"),
    ("bucket_clank", 565968, "melle_teich", "Small metal bucket being picked up"),
    ("dog_bark", 277058, "kwahmah_02", "Single Dog Bark"), ("dog_bark", 495658, "aunrea", "Dog Bark"),
    ("goat_bleat", 677218, "satoristudios3", "mini Goat Baa"), ("goat_bleat", 581240, "Kinoton", "Single Goat Bleating 2x"),
    ("goat_bleat", 200333, "jsbarrett", "Baby goat bleating"),
    ("cow_moo", 546481, "invertedturtle", "Cow Moo"), ("cow_moo", 546479, "invertedturtle", "Cow Moo 2"),
    ("cow_moo", 513565, "spurioustransients", "Cow moo #8"),
    ("birds", 327447, "freelibras", "Birds Chirping on a Tree 3"),
    ("birds", 690626, "Audiobaaz911", "North India Countryside Birds chirping"),
    ("koel", 460466, "ramblinglibrarian", "Koel-01"), ("crow", 813115, "qubodup", "Crow Caw"),
    ("peacock", 688203, "Kinoton", "Bird, Peacock Call"), ("peacock", 864292, "TheKingOfGeeks360", "Indian Peafowl short squawk"),
    ("rooster", 435508, "BenjaminNelan", "Rooster Crow 1"), ("rooster", 154957, "signorvaso", "brahma-rooster"),
    ("temple_bell", 271627, "LoopUdu", "2 Hindu Temples Bells"), ("temple_bell", 668647, "tec_studio", "temple_bell_002"),
    ("rain", 666624, "EricsSoundschmiede", "Heavy Rain"), ("rain", 592485, "Azrai93", "Light Rain In Ipoh City"),
    ("thunder", 399656, "bajko", "sfx_thunder blast"), ("thunder", 169534, "klankbeeld", "high thunder suburb 08"),
    ("wind", 438886, "craigsmith", "Light Outdoor Wind"), ("wind", 182123, "Julien%20Nicolas", "mega wind 01"),
    ("crowd_laugh", 588394, "FunWithSound", "Laugh Crowd Soft"), ("crowd_laugh", 138112, "snakebarney", "Small Crowd Laughing"),
    ("crowd_laugh", 383207, "Kinoton", "Sitcom Laughter 9x, Small Audience"),
    ("footsteps_mud", 488068, "BenDrain", "Footsteps_Mud_01"), ("footsteps_mud", 488082, "BenDrain", "Footsteps_Mud_Single_03"),
    ("door_creak", 475485, "o_ciz", "Door_wood_creak_1"), ("door_creak", 125957, "Ryding", "Opening a creaking door"),
    ("whoosh", 449996, "DJT4NN3R", "whoosh_short_mid"), ("whoosh", 423799, "ch_ase", "Little Whoosh 2"),
    ("whoosh", 486234, "BennettFilmTeacher", "Whoosh For Whip Zoom"),
    ("bat_hit", 851452, "hashtagsmcgee", "Bat_hit2"), ("bat_hit", 457039, "Breviceps", "Hit a ball"),
    ("bat_hit", 594342, "GH0STY_XD", "Cricket ball bouncing on a bat"),
    ("glass_clink", 868468, "sokworks", "Glass Clink 3"), ("glass_clink", 349691, "Mikes-MultiMedia", "clink glasses"),
    ("bicycle_bell", 156064, "marcolo91", "bicycle bell"), ("bicycle_bell", 383631, "newagesoup", "bicycle-bell_19"),
    ("bicycle_bell", 431320, "Kinoton", "Bicycle Bell Ringing"),
    ("horn", 563346, "Anzbot", "BEEP BEEP"), ("horn", 423990, "AmishRob", "Car horn beep beep two beeps"),
    ("rickshaw_ambience", 576485, "TRP", "India, rickshaw ride, engine, traffic, horns, Calcutta"),
    ("sizzle", 239639, "applauseav", "BACON FRYING SIZZLE POP"), ("sizzle", 616820, "TRP", "Cooking, gas stove, sizzles, wok, frying"),
    ("kettle_whistle", 322953, "crharvey12", "kettle.whistle"),
    ("pouring_water", 336386, "moai15", "Pouring_Water_04"), ("pouring_water", 763461, "FOSSarts", "pouring water on grass - 1"),
    ("pouring_water", 482857, "craigsmith", "Water Poured from Bottle"),
    ("cartoon_whistle", 518104, "se2001", "Cartoon Falling Whistle"), ("cartoon_whistle", 403002, "martian", "classic dizzy take slide whistle"),
    ("cartoon_whistle", 517633, "SamuelGremaud", "SLIDE WHISTLE - 1"), ("cartoon_fall", 395443, "plasterbrain", "Cartoon Fall"),
    ("pop", 245646, "unfa", "Cartoon Pop (Distorted)"), ("pop", 202230, "deraj", "Pop sound"), ("pop", 328119, "D.S.G.", "Pop 9"),
    ("ding", 611113, "5ro4", "bell ding 1"), ("ding", 332518, "achinverma", "simple ding"),
    ("sad_trombone", 175409, "kirbydx", "wah wah sad trombone"), ("sad_trombone", 362206, "TaranP", "horn_fail_wahwah_1"),
    ("bonk", 871191, "cb9382", "Comedic Loud Bonk"), ("bonk", 262703, "xela_sonitus", "bonk"),
    ("crickets_night", 522299, "Defelozedd94", "Crickets At Night - Raw sound"),
    # --- second batch: everything stories/hindi/ASSET_NEEDS.md asks for (verified CC0 on 2026-10-02) ---
    ("snore", 760036, "stevielematt", "SNORE-03"), ("snore", 432996, "mattyharm", "Male Snore 2"),
    ("dog_snore", 509548, "hinchinbrook", "Small Dog Snoring"), ("dog_snore", 543645, "5ound5murf23", "Dog Snore 1"),
    ("dog_sniff", 528939, "fthgurdy", "Dog sniff 2"), ("dog_sniff", 595826, "binxa", "Dog Sniff"),
    ("dog_whine", 701268, "5ro4", "dog whining"), ("dog_whine", 505827, "jedg", "dog whine"),
    ("dog_yelp", 160478, "unfa", "Dog's Yelping 7"), ("dog_yawn", 827660, "qubodup", "Dog Yawn"),
    ("chew", 257704, "vmgraw", "Candy Bar Chewing"), ("chew", 542682, "BonginkosiMakhubu190225", "Crunchy chewing"),
    ("chew", 653727, "soupods", "cow chewing corn"),
    ("crunch", 749872, "NinjaSharkStudios", "Chip Crunch"), ("crunch", 723609, "Rookster", "Apple Crunching"),
    ("slurp", 426324, "MTJohnson", "Slurp"), ("slurp", 568043, "benkenart", "coffee slurp 5"),
    ("stomach", 447911, "Breviceps", "Growling stomach / Stomach rumbles"), ("stomach", 615774, "oldrascal", "Stomach Growl"),
    ("gulp", 531755, "magnuswaker", "Gulp - Hard Swallow"), ("gulp", 418853, "Wizage", "clean wet gulps"),
    ("glug", 532749, "iwanPlays", "glug glug glug"), ("glug", 485461, "thomas_weakley", "Chugging Water - Glug Glug Glug Ahhh"),
    ("drip", 612596, "diogorusso", "water dripping short"), ("drip", 219373, "bushi3593", "water dripping in faucet 1"),
    ("tap", 212177, "OwlStorm", "Tap Water 1"), ("tap", 347941, "grizzlypwn", "Closing water tap"),
    ("rope_creak", 861827, "qubodup", "Creaking Metal Wire of Wooden Gate"),
    ("squelch", 207142, "ahill86", "MudSquelch"), ("squelch", 516643, "LucasDuff", "Squelch"), ("squelch", 683520, "eqavox", "Feet Squelch"),
    ("splat", 445118, "Breviceps", "Cartoon - Splat!"), ("splat", 460876, "moshang", "splat11"),
    ("flies", 390733, "FunWithSound", "Buzzing Insect Short"), ("flies", 866635, "hz37", "Two flies buzzing on a hot day"),
    ("owl", 465697, "Breviceps", "Owl Hoot"), ("owl", 528623, "dandman3039", "Owl Slow Hoot"),
    ("bangles", 646777, "pbimal", "churaa-01"), ("bangles", 175435, "breglad15", "Bangles"),
    ("chalk", 656044, "nayahnaidoo", "Drawing on a chalk board"),
    ("knock", 629987, "Flem0527", "Knocking on Wood Door (1)"), ("knock", 268500, "wjtaylor", "door_knock"),
    ("door_slam", 724123, "saha213131", "Door slam"),
    ("shop_bell", 57743, "3bagbrew", "shop_door_bell"), ("shop_bell", 556710, "NachtmahrTV", "Shop Bell"),
    ("coin", 630018, "Flem0527", "Singular Coin Dropping"), ("coin", 510735, "HoseNoseSounds", "Coin dropped on table 5"),
    ("coin_jar", 591596, "painted-panda", "Rattle of Coins in a Jar"),
    ("paper_rip", 342541, "sgrowe", "Fast Paper Rip"), ("paper_rip", 136496, "zachfbstudios", "Paper rip 1"),
    ("paper_flutter", 382654, "bbrocer", "Paper Fluttering"), ("paper_flutter", 320913, "mickdow", "Paper Flutter"),
    ("umbrella", 792526, "randbsoundbites", "Opening an umbrella"), ("umbrella", 181909, "CapsLok", "Umbrella Open"),
    ("balloon_squeak", 511673, "jerry.berumen", "balloon funny sounds"), ("balloon_squeak", 649325, "Thimras", "Balloon squeaks"),
    ("balloon_deflate", 326756, "hareball101", "balloon deflate"), ("balloon_deflate", 82129, "Gniffelbaf", "Balloon-Deflate-08-Long"),
    ("snap", 251464, "martian", "twig snap classic"), ("snap", 82802, "payattention", "stick snap"),
    ("ref_whistle", 538422, "Rosa-Orenes256", "Referee whistle sound"), ("ref_whistle", 218318, "SpliceSound", "Referee whistle blow, gymnasium"),
    ("mic_feedback", 411441, "CreationsByJacobFilms", "Microphone Feedback"), ("mic_feedback", 673590, "Bmangelo", "Mic feedback D short"),
    ("phone_ring", 528111, "fspera", "Phone Ringing Sound"), ("phone_ring", 610191, "BennettFilmTeacher", "Old Phone Ringing"),
    ("switch", 348225, "tbrook", "Switch Light 05"), ("switch", 788643, "Philip_Berger", "Light Switch on"),
    ("hammer", 513346, "se2001", "Hammering Nail"), ("hammer", 707983, "KaylinSchafer", "Hitting a nail with a hammer"),
    ("window_rattle", 371256, "risto_alcinov", "Residential staircase window rattle"),
    ("clay_pot", 399080, "Kinoton", "Clay Pottery Drop n Break"), ("clay_pot", 453846, "kyles", "large ceramic clay pot open close lid"),
    ("leaves", 862894, "lreeve", "Dry leaves rustle and break"), ("leaves", 475425, "o_ciz", "Tree branch_1 (leaves, rustle)"),
    ("hay", 770112, "Vrymaa", "Plants or ferns - Manipulation & Hit"),
    ("march_drums", 870501, "CHallSmith", "Marching Drums in Parade with Crowd"),
    ("kids_laugh", 616088, "medyk3D", "Child's laugh 1"), ("kids_laugh", 642516, "kikorurelas", "Kids laughing"),
    ("applause", 606967, "Department64", "Audience Clapping 03h"), ("applause", 25292, "freesound", "Bye_Bye_Claps_ses1"),
    ("cheer", 511788, "Kinoton", "Crowd Cheering Yahoo"), ("cheer", 264377, "HowardV", "small crowd cheering"),
    ("gasp", 635110, "RadioCounseling", "Crowd gasp"), ("gasp", 232472, "Reitanna", "surprised gasps"),
    ("grunt", 507730, "Keskaowl", "EffortNoise"), ("grunt", 680135, "DeqstersLab", "Grunting effort pushing something"),
    ("sneeze", 185415, "unfa", "Sneeze Shot"), ("sneeze", 524835, "SamuelGremaud", "SNEEZE - 2"),
    ("teeth", 517676, "danlucaz", "Chattering Teeth"), ("teeth", 509875, "se2001", "Teeth Chatter"),
    ("nose_blow", 433588, "jackthemurray", "Blowing Nose"), ("nose_blow", 524831, "SamuelGremaud", "BLOWING NOSE - 1"),
    ("burp", 399768, "tehteho", "Burp 9"), ("burp", 814323, "Sadiquecat", "Burp - medium-deep"),
    ("mela", 653920, "IENBA", "Small Crowd Walla"),
    ("village_day", 553079, "kalhan", "Raigarh Village Early Afternoon"), ("village_day", 562181, "Anzbot", "Goat Herders whistling, dogs barking"),
    ("village_night", 130412, "Abinash87", "Night cricket ambience"),
    ("dhol", 418780, "rsn267", "Indian Wedding Dhols"), ("dhol", 865161, "qubodup", "Maybe Dollak Drum Freestyle Jamming"),
    ("dholak", 536872, "curesforbrokenhearts", "DHOLAK (BASS SKIN)"),
    ("tabla", 418377, "Ninad_P", "tabla_na"), ("tabla", 689551, "Sh%C5%8Dtotsu", "Tabla (Short)"),
    ("bansuri", 448458, "Ninad_P", "bansuri_flute_rag_jog"),
    ("train_whistle", 633869, "deleted_user_13502068", "flute train whistle"), ("train_whistle", 264321, "olliehahn12", "Train Whistle"),
    ("gong", 803159, "kerozenne", "Temple Gong 2"), ("tada", 376318, "jimhancock", "TaDa!"),
    ("chimes", 437337, "giddster", "Wind chimes 1"),
    ("twinkle", 578803, "nomiqbomi", "Sparkle"), ("twinkle", 462094, "LilMati", "Sparkling Star 02"),
    ("poof", 343959, "Reitanna", "poof"), ("poof", 643876, "sushiman2000", "Smoke Poof"),
    ("wrapper", 269338, "BluetoothBoy", "Candy Wrapper Crinkle"), ("wrapper", 508268, "aerolus", "wrapper crinkle"),
    ("bottle_crunch", 762424, "FOSSarts", "quick crunch of empty plastic water bottle - 1"),
]

# ffmpeg recipes for sounds that are better MADE from the library than searched for.  Use: ffmpeg -i in.mp3 -af "<filter>" out.wav
FFMPEG = {
    "well_echo": "aecho=0.8:0.88:320|640|960:0.5|0.32|0.18",                       # 'में' -> 'ऊँऊँ-मेंऽऽ' inside the well
    "mela_echo": "aecho=0.8:0.9:700|1400|2100:0.45|0.25|0.12",                     # 'भूख लगी है... लगी है... है...' across the mela
    "megaphone": "highpass=f=500,lowpass=f=3200,acrusher=bits=10:mix=0.25,aecho=0.8:0.6:180|360:0.35|0.15",
    "muffled_in_tin": "lowpass=f=900,aecho=0.7:0.6:15|28:0.6|0.4",                  # goat bleating inside a tin / bucket on the head
    "pitch_up_small": "asetrate=44100*1.35,aresample=44100,atempo=0.8",            # smaller/cuter creature, same length
    "pitch_down_big": "asetrate=44100*0.75,aresample=44100,atempo=1.3",            # bigger/sulkier
    "tiny_fast": "asetrate=44100*2,aresample=44100",                               # ant drums from a dholak/tabla hit
    "hooves_from_wood_steps": "asetrate=44100*1.6,aresample=44100,atempo=1.25",    # goat trot from kenney footstep_wood / impactWood_light
    "musical_drip": "asetrate=44100*{ratio},aresample=44100",                      # TING-TUNG-TONG: ratio 1.0/1.26/1.5 on one drip
    "slow_motion": "asetrate=44100*0.6,aresample=44100",
}

# stories/hindi/ASSET_NEEDS.md "Sound effects and music" ids -> which buckets of files serve them
STORY = {
    "sfx_fall_thud": {"from": ["thud", "impact", "cartoon_fall"]},
    "sfx_bonk_boing": {"from": ["bonk", "boing", "bat_hit"]},
    "sfx_whoosh_swish": {"from": ["whoosh", "cloth_rustle"]},
    "sfx_slip_slide": {"from": ["slip", "cartoon_whistle"]},
    "sfx_poof_puff": {"from": ["poof"]},
    "sfx_splash": {"from": ["splash"]},
    "sfx_mud_splat": {"from": ["squelch", "splat", "footsteps_mud"]},
    "sfx_drips_tap": {"from": ["drip"], "procedural": {"musical_drip": FFMPEG["musical_drip"]}, "note": "TING-TUNG-TONG roof drips = one drip at 3 pitches."},
    "sfx_water_flow_spray": {"from": ["tap", "pouring_water"]},
    "sfx_glug_gulp": {"from": ["gulp", "glug"]},
    "sfx_well_rope_pulley": {"from": ["rope_creak", "creak", "bucket_clank"], "note": "No CC0 recording of a rope over a well pulley; a creaking gate wire + Kenney creaks stand in."},
    "sfx_echo_reverb": {"from": [], "procedural": {k: FFMPEG[k] for k in ("well_echo", "mela_echo", "megaphone")}, "note": "Make it: run the dialogue line through one of these ffmpeg filters."},
    "sfx_rain_thunder": {"from": ["rain", "thunder"]},
    "sfx_wind_leaves": {"from": ["wind", "leaves"]},
    "sfx_crickets_owl_night": {"from": ["crickets_night", "owl", "village_night"]},
    "sfx_birds_crow_rooster": {"from": ["birds", "crow", "rooster", "koel", "peacock"]},
    "sfx_flies_buzz": {"from": ["flies"]},
    "sfx_goat_bleat": {"from": ["goat_bleat"], "procedural": {k: FFMPEG[k] for k in ("pitch_up_small", "pitch_down_big", "muffled_in_tin", "well_echo")},
                       "note": "Only 3 real bleats; build the 10+ variant library with these filters (cheeky = pitch_up_small, sulky = pitch_down_big, inside a tin = muffled_in_tin, in the well = well_echo)."},
    "sfx_goat_hooves_burp": {"from": ["burp"], "procedural": {"hooves_from_wood_steps": FFMPEG["hooves_from_wood_steps"]},
                             "note": "No CC0 goat-hoof recording found; pitch Kenney footstep_wood/impactWood_light up (filter given). Burp is human."},
    "sfx_chew_munch": {"from": ["chew", "crunch", "paper_rip"]},
    "sfx_dog_snore": {"from": ["dog_snore", "snore"]},
    "sfx_dog_sniff_bark": {"from": ["dog_sniff", "dog_bark"]},
    "sfx_dog_misc": {"from": ["dog_whine", "dog_yelp", "dog_yawn"], "note": "Tail thump = Kenney impactSoft; dog sneeze = human sneeze with pitch_up_small."},
    "sfx_cow_moo": {"from": ["cow_moo"]},
    "sfx_stomach_rumble": {"from": ["stomach"]},
    "sfx_food_crunch_slurp": {"from": ["crunch", "slurp", "chew"]},
    "sfx_sticky": {"from": ["squelch", "pop"], "note": "Pull-apart squelch + pop; no dedicated syrup recording."},
    "sfx_frying_jalebi": {"from": ["sizzle"]},
    "sfx_wrapper_crinkle": {"from": ["wrapper", "bottle_crunch"]},
    "sfx_metal_bucket_clang": {"from": ["bucket_clank", "metal_clank"]},
    "sfx_bucket_drum": {"from": ["metal_clank", "bucket_clank"], "note": "Play Kenney impactMetal/impactTin hits in rhythm."},
    "sfx_kitchen_metal": {"from": ["metal_clank", "glass_clink"]},
    "sfx_bangles": {"from": ["bangles"]},
    "sfx_school_chalk_slate": {"from": ["chalk", "wood_tap", "plate"], "note": "Chalk is a drawing scratch, not a squeak; slate clatter = Kenney impactWood_light/impactPlate."},
    "sfx_doors_knocks_bells": {"from": ["knock", "door_slam", "shop_bell", "door_creak"]},
    "sfx_coins": {"from": ["coin", "coin_jar", "coins"]},
    "sfx_paper_flutter_rip": {"from": ["paper_rip", "paper_flutter"]},
    "sfx_kite": {"from": ["paper_flutter", "whoosh"], "note": "Kite = paper flutter + whoosh; no real kite recording."},
    "sfx_umbrella": {"from": ["umbrella"]},
    "sfx_balloon": {"from": ["balloon_squeak", "balloon_deflate"]},
    "sfx_snap_crack": {"from": ["snap"]},
    "sfx_whistle": {"from": ["ref_whistle", "cartoon_whistle"]},
    "sfx_megaphone_mic": {"from": ["mic_feedback"], "procedural": {"megaphone": FFMPEG["megaphone"]}},
    "sfx_phone": {"from": ["phone_ring", "low_battery"]},
    "sfx_power_cut": {"from": ["switch"]},
    "sfx_hammer": {"from": ["hammer"]},
    "sfx_misc_objects": {"from": ["window_rattle", "clay_pot", "tap"]},
    "sfx_hay_rustle": {"from": ["hay", "leaves"]},
    "sfx_ant_drums": {"from": ["march_drums", "dholak", "tabla"], "procedural": {"tiny_fast": FFMPEG["tiny_fast"]}, "note": "Pitch a dholak/tabla hit up an octave and loop it."},
    "sfx_human_reactions": {"from": ["kids_laugh", "crowd_laugh", "applause", "cheer", "gasp", "grunt"]},
    "sfx_human_body": {"from": ["snore", "sneeze", "teeth", "nose_blow"]},
    "sfx_crowd_mela_ambience": {"from": ["mela", "dhol", "cheer", "kids_laugh"]},
    "sfx_ambience_village": {"from": ["village_day", "village_night", "birds", "rain"]},
    "music_dhol_dholak_flute": {"from": ["dhol", "dholak", "tabla", "bansuri"], "note": "Real dhol/dholak recordings + a 4 s bansuri phrase; no finished happy cue - needs composing."},
    "music_stings_comic": {"from": ["jingles", "sad_trombone", "gong", "tada", "cartoon_whistle"], "note": "Kenney Music Jingles (CC0): HIT/PIZZI/NES/SAX/STEEL stings."},
    "music_mood_beds": {"from": ["chimes"], "note": "Only wind chimes for the dream bed; scary 'ढुम्म' and detective 'टिंग-टिंग' beds are missing."},
    "music_magic_ting": {"from": ["twinkle", "ding"]},
    "music_train_whistle": {"from": ["train_whistle"]},
    "music_series_theme": {"from": [], "note": "Needs an original composition - no stock CC0 theme should be the series identity."},
}

# needs that Kenney filenames can fill: need -> (regex on "pack/file" path, lower-case)
KENNEY_RULES = {
    "impact": r"impact(generic|plank|wood|soft|punch)",
    "thud": r"impactsoft_heavy|impactpunch_heavy|impactsoft_medium",
    "metal_clank": r"impactmetal|metalclick|metalpot|metallatch",
    "glass_clink": r"impactglass|glass",
    "footsteps": r"footstep",
    "door_creak": r"creak|door",
    "click": r"click",
    "pop": r"(^|/)pop|bong",
    "ding": r"confirmation|ding|bell",
    "whoosh": r"swish|whoosh|cloth",
    "coins": r"coin|chips",
    "jump": r"jump",
    "laser_zap": r"laser|zap",
    "error_buzz": r"error|buzz",
    "voice_numbers_words": r"voiceover",
    "jingles": r"jingles_",
    "cloth_rustle": r"cloth",
    "bell": r"bell",
    "creak": r"rpg-audio/.*creak",
    "wood_tap": r"impactwood_light|impactplank",
    "plate": r"impactplate",
    "low_battery": r"lowdown|lowthreetone",
}

NEEDS = ["boing", "slip", "splash", "bucket_clank", "dog_bark", "goat_bleat", "cow_moo", "birds", "rooster", "temple_bell",
         "rain", "thunder", "wind", "crowd_laugh", "footsteps_mud", "door_creak", "kite_string_whoosh", "bat_hit",
         "glass_clink", "bicycle_bell", "auto_rickshaw_horn", "sizzle", "pouring_water", "cartoon_whistle", "pop", "ding",
         "sad_trombone", "impact", "thud", "whoosh", "footsteps", "click", "bonk", "cartoon_fall", "koel", "crow", "peacock",
         "kettle_whistle", "crickets_night", "metal_clank", "drip", "mud_splat", "dhol_drum", "shehnai_fanfare", "kid_giggle",
         "tabla_hit", "gulp", "sneeze", "burp", "snore"]
# a need may be satisfied by another bucket that really is the same kind of sound
ALIASES = {"kite_string_whoosh": ["whoosh"], "auto_rickshaw_horn": ["horn", "rickshaw_ambience"], "mud_splat": ["squelch", "splat"],
           "dhol_drum": ["dhol", "dholak"], "kid_giggle": ["kids_laugh"], "tabla_hit": ["tabla"]}
# honest notes for needs we only partly cover
NOTES = {"auto_rickshaw_horn": "No isolated CC0 auto-rickshaw horn found; 'horn' = generic small car beeps, 'rickshaw_ambience' = a 67 s "
                               "Calcutta rickshaw ride with real horns (cut a horn out of it).",
         "kite_string_whoosh": "Generic whooshes; no recording of an actual kite string (manja).",
         "bat_hit": "Baseball/ball hits plus a cricket ball bounced on a bat; no clean leather-on-willow cricket shot."}


def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                d = r.read(); return d if binary else d.decode("utf-8", "replace")
        except Exception as ex:
            if i == tries - 1: raise
            print("   retry", url, ex); time.sleep(2 + 3 * i)


def fetch_kenney(lic_parts):
    for slug in KENNEY:
        dest = os.path.join(SFX, "kenney", slug)
        page_url = f"https://kenney.nl/assets/{slug}"
        if os.path.isdir(dest) and any(f.lower().endswith((".ogg", ".wav", ".mp3")) for _, _, fs in os.walk(dest) for f in fs):
            print("kenney", slug, "already there")
        else:
            try:
                page = get(page_url)
            except Exception as ex:
                print("kenney", slug, "PAGE FAILED", ex); continue
            m = re.search(r"""href=['"](https://kenney\.nl/media/pages/assets/[^'"]+?\.zip)['"]""", page)
            if not m:
                print("kenney", slug, "no zip link found on", page_url); continue
            if "publicdomain/zero" not in page and "CC0" not in page:
                print("kenney", slug, "page does not say CC0 - skipped"); continue
            print("kenney", slug, "<-", m.group(1))
            z = zipfile.ZipFile(io.BytesIO(get(m.group(1), binary=True)))
            os.makedirs(dest, exist_ok=True); z.extractall(dest)
            print("   extracted", len(z.namelist()), "entries")
        lic = None
        for root, _, fs in os.walk(dest):
            for f in fs:
                if f.lower().startswith("license") and f.lower().endswith(".txt"):
                    lic = open(os.path.join(root, f), encoding="utf-8", errors="replace").read().strip(); break
            if lic: break
        lic_parts.append(f"### Kenney - {slug}\n\nSource page: {page_url}  \nFolder: `sfx/kenney/{slug}/`\n\n"
                         + ("License.txt shipped in the zip:\n\n```\n" + lic + "\n```\n" if lic else "_(no License.txt found in the zip; the page states CC0)_\n"))


def fetch_freesound():
    out = os.path.join(SFX, "freesound"); os.makedirs(out, exist_ok=True)
    meta_path = os.path.join(out, "freesound_meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    for need, sid, user, title in FREESOUND:
        fn = f"{need}_{sid}.mp3"; path = os.path.join(out, fn)
        page_url = f"https://freesound.org/people/{user}/sounds/{sid}/"
        if os.path.exists(path) and str(sid) in meta:
            continue
        try:
            page = get(page_url)
        except Exception as ex:
            print("freesound", sid, "PAGE FAILED", ex); continue
        lics = set(re.findall(r"creativecommons\.org/(?:licenses|publicdomain)/[a-z\-]+/[0-9.]+", page))
        if lics != {"creativecommons.org/publicdomain/zero/1.0"}:
            print("freesound", sid, "licence is", lics, "- NOT CC0, skipped"); continue
        prev = re.findall(r"https://cdn\.freesound\.org/previews/[^\"'\s]+-hq\.mp3", page)
        if not prev:
            print("freesound", sid, "no preview url"); continue
        dur = re.findall(r"(?i)duration[^0-9]{0,80}([0-9.]+)", page)
        if not os.path.exists(path):
            open(path, "wb").write(get(prev[0], binary=True))
            print("freesound", need, sid, "->", fn, os.path.getsize(path) // 1024, "KB")
        meta[str(sid)] = {"need": need, "file": f"sfx/freesound/{fn}", "title": title, "author": html.unescape(user.replace("%20", " ")),
                          "url": page_url, "preview": prev[0], "duration_s": float(dur[0]) if dur else None,
                          "licence": CC0, "checked": datetime.date.today().isoformat()}
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), indent=1)
        time.sleep(0.5)
    return meta


def build_catalogue():
    meta_path = os.path.join(SFX, "freesound", "freesound_meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    buckets = {}
    for sid, m in meta.items():
        if os.path.exists(os.path.join(HERE, m["file"])):
            buckets.setdefault(m["need"], []).append({"file": m["file"], "source": "freesound", "title": m["title"], "author": m["author"],
                                                      "url": m["url"], "duration_s": m.get("duration_s"), "licence": m["licence"]})
    kroot = os.path.join(SFX, "kenney")
    kfiles = []
    for root, _, fs in os.walk(kroot):
        for f in sorted(fs):
            if f.lower().endswith((".ogg", ".wav", ".mp3")) and not f.lower().startswith("preview"):
                kfiles.append(os.path.relpath(os.path.join(root, f), HERE).replace(os.sep, "/"))
    for need, rx in KENNEY_RULES.items():
        hits = [p for p in kfiles if re.search(rx, p.lower().split("sfx/kenney/", 1)[1])]
        if need == "click": hits = [p for p in hits if "interface" in p or "ui-audio" in p]
        if need in ("whoosh", "cloth_rustle"): hits = [p for p in hits if "voiceover" not in p]
        for p in hits[:200 if need in ("jingles", "voice_numbers_words") else 12]:
            buckets.setdefault(need, []).append({"file": p, "source": "kenney/" + p.split("/")[2], "licence": CC0})
    needs = {}
    for n in NEEDS + sorted(k for k in buckets if k not in NEEDS):
        items = list(buckets.get(n, []))
        for a in ALIASES.get(n, []): items += buckets.get(a, [])
        if items: needs[n] = {"files": items, **({"note": NOTES[n]} if n in NOTES else {})}
    missing = [n for n in NEEDS if n not in needs]
    story, story_missing, story_proc_only = {}, [], []
    for sid, spec in STORY.items():
        files, seen = [], set()
        for b in spec["from"]:
            for it in buckets.get(b, []):
                if it["file"] not in seen: seen.add(it["file"]); files.append(dict(it, bucket=b))
        entry = {"files": files}
        if spec.get("procedural"): entry["procedural_ffmpeg_af"] = spec["procedural"]
        if spec.get("note"): entry["note"] = spec["note"]
        story[sid] = entry
        if not files and spec.get("procedural"): story_proc_only.append(sid)
        elif not files: story_missing.append(sid)
    cat = {"generated": datetime.date.today().isoformat(), "licence_summary": "Every file listed is CC0 (public domain). See sfx/LICENSES.md.",
           "how_to_use_procedural": "ffmpeg -i <file> -af \"<filter>\" out.wav  (filters under procedural_ffmpeg_af / ffmpeg_recipes)",
           "ffmpeg_recipes": FFMPEG,
           "story_ids": story, "story_missing": story_missing, "story_procedural_only": story_proc_only,
           "needs": needs, "missing": missing, "kenney_file_count": len(kfiles), "freesound_file_count": len(meta)}
    json.dump(cat, open(os.path.join(SFX, "catalogue.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("catalogue:", len(needs), "needs covered,", len(kfiles), "kenney files,", len(meta), "freesound files")
    print("missing:", ", ".join(missing) or "nothing")
    print("story ids:", len(story) - len(story_missing) - len(story_proc_only), "with files,", "procedural only:", story_proc_only, "missing:", story_missing)
    thin = [k for k, v in story.items() if 0 < len(v["files"]) < 2]
    if thin: print("story ids with only one file:", thin)
    return cat


def write_licences(kenney_parts, meta):
    rows = "\n".join(f"| `{m['file']}` | {m['title']} | {m['author']} | [{k}]({m['url']}) | CC0 1.0 |" for k, m in sorted(meta.items(), key=lambda kv: kv[1]["file"]))
    txt = f"""# Sound-effect licences (generated by fetch_sfx.py on {datetime.date.today().isoformat()})

Everything in `sfx/` is **CC0 1.0 Universal (public domain dedication)** - free for commercial use, including monetised
YouTube videos, no attribution required (crediting Kenney / Freesound authors is a nice courtesy, not an obligation).
Nothing licensed BY, BY-NC, "royalty free with restrictions" or unclear is downloaded by this script.

## 1. Kenney audio packs (kenney.nl)

Each pack page says "CC0 licensed" and each zip ships a License.txt, copied verbatim below.

{chr(10).join(kenney_parts)}

## 2. Freesound (freesound.org) - curated CC0 sounds

Each sound was checked by hand on 2026-10-02 and is re-checked by `fetch_sfx.py` before download: the script only keeps a
sound whose public page links to exactly one licence, `creativecommons.org/publicdomain/zero/1.0`. Freesound's FAQ:
"for the 'zero' license you can do pretty much what you want with the sound. You could even sell the sound" (you may not
claim authorship). We download Freesound's public HQ preview MP3 (originals need a logged-in account; download them by
hand from the URL below if you ever need the lossless file).

| file | title | author | page | licence |
|---|---|---|---|---|
{rows}

## 3. Sources checked but NOT auto-downloaded

* **Sonniss #GameAudioGDC bundles** (https://sonniss.com/gameaudiogdc, licence https://sonniss.com/gdc-bundle-license/):
  "Licensee may use and modify the licensed sound effects for personal and commercial projects without attribution", but
  "Licensee may not distribute, publish, sub-license or otherwise supply the sound effects as sound effects to any other
  person" and it is "expressly prohibited" to use them "for the purpose of training artificial intelligence technologies".
  Fine for our finished videos, but the bundles are tens of GB and must not be put in a public repo -> manual download only,
  keep outside git.
* **BBC Sound Effects** (RemArc licence) - non-commercial only. Excluded.
* **Freesound sounds licensed CC-BY / CC-BY-NC / Sampling+** - excluded (the script refuses anything that is not CC0).
"""
    open(os.path.join(SFX, "LICENSES.md"), "w", encoding="utf-8").write(txt)
    print("wrote sfx/LICENSES.md")


if __name__ == "__main__":
    os.makedirs(SFX, exist_ok=True)
    meta = {}
    if "--catalogue" not in sys.argv:
        parts = []
        fetch_kenney(parts)
        meta = fetch_freesound()
        write_licences(parts, meta)
    build_catalogue()
