#/bin/bash
INPUT=$1
OUTPUT="${1%%.*}-fade.${1#*.}"
LEN=${2:-2}
 
DURATION=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=duration \
  -of default=nw=1:nk=1 "$INPUT")
# echo $DURATION
D=$(echo $DURATION-$LEN | bc)
echo $D
ffmpeg -hide_banner -v error -stats \
  -i "$INPUT" \
  -vf fade=in:d=$LEN,fade=out:st=$D:d=$LEN \
  -af afade=in:d=$LEN,afade=out:st=$D:d=$LEN \
  "$OUTPUT"
