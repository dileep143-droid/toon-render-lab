#!/bin/bash
# decrypt every md-*/md.enc artifact (AES-256, key in $MP_KEY) and merge them into <dst> (md/<pack>/*.npz + catalogue_*.json).
# usage: decrypt_all.sh <src_dir> <dst>   - if ./enc_old exists (artifacts of an earlier run) it is unpacked FIRST, so this run's
# rebuilt packs overwrite it.
SRC=$1; DST=$2; mkdir -p $DST
for d in enc_old $SRC; do
  [ -d "$d" ] || continue
  for f in $(find $d -name 'md.enc' | sort); do
    t=$(mktemp -d)
    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MP_KEY -in "$f" | tar -xf - -C $t && cp -r $t/out/. $DST/ || echo "DECRYPT FAIL $f"
    rm -rf $t
  done
done
echo "decrypted: $(find $DST -name '*.npz' | wc -l) motion files, $(ls $DST/catalogue_*.json 2>/dev/null | wc -l) catalogue parts"
