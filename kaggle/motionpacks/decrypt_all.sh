#!/bin/bash
# decrypt every md-*/md.enc artifact (AES-256, key in $MP_KEY) and merge them into <dst> (md/<pack>/*.npz + catalogue_*.json)
SRC=$1; DST=$2; mkdir -p $DST
for f in $(find $SRC -name 'md.enc'); do
  t=$(mktemp -d)
  openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MP_KEY -in "$f" | tar -xf - -C $t && cp -r $t/out/. $DST/ || echo "DECRYPT FAIL $f"
  rm -rf $t
done
echo "decrypted: $(find $DST -name '*.npz' | wc -l) motions, $(ls $DST/catalogue_*.json 2>/dev/null | wc -l) catalogue parts"
