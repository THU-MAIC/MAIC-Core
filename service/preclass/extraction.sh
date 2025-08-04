# Build Container
# docker build -t libreoffice-converter .


SOURCE_FILE=$1
FILENAME=$(basename "$SOURCE_FILE")
BASENAME="${FILENAME%.*}"

# Make Buffer Directory
mkdir -p buffer/${BASENAME}
rm -rf buffer/${BASENAME}/*

echo "## Copying File"
cp ${SOURCE_FILE} ./buffer/${BASENAME}/presentation.pptx

echo "## Extracting File Contents"
# Convert From PPTX to PDF
docker run --rm  -v $(pwd)/buffer/${BASENAME}:/data preclass-converter libreoffice --headless --convert-to pdf --outdir pdf presentation.pptx

# Convert From PDF to PNG
python3 -m scripts.pdf2png --input_file buffer/${BASENAME}/pdf/presentation.pdf --output_dir buffer/${BASENAME}/pngs

# Extract Text
python3 -m scripts.ppt2text --ppt_path buffer/${BASENAME}/presentation.pptx --png_path buffer/${BASENAME}/pngs --out_path buffer/${BASENAME}/result.jsonl

# Generate Teaching Actions
echo "## Generating Teaching Actions"

## Summarization
echo "### Doing Description"
python3 -m scripts.preprocess --info_path buffer/${BASENAME}/result.jsonl --save_path buffer/${BASENAME}/summarized_script.jsonl

## Segment Script
echo "### Doing Segmentation"
python3 -m scripts.structurelize \
	--info_path buffer/${BASENAME}/summarized_script.jsonl \
	--save_path buffer/${BASENAME}/segmented_script.pkl \
	--title ${BASENAME}

## ShowFile Generation
echo "### Generating ShowFile"
python3 -m scripts.gen_showfile \
	--input_path buffer/${BASENAME}/segmented_script.pkl \
	--save_path buffer/${BASENAME}/with_showfile.pkl

## ReadScript Generation
echo "### Generating ReadScript"
python3 -m scripts.gen_readscript \
	--input_path buffer/${BASENAME}/with_showfile.pkl \
	--save_path buffer/${BASENAME}/with_readscript.pkl

## AskQuestion Generation
echo "### Generating AskQuestion"
python3 -m scripts.gen_askquestion \
	--input_path buffer/${BASENAME}/with_readscript.pkl \
	--save_path buffer/${BASENAME}/final_result.pkl \
	--print_path buffer/${BASENAME}/printed_final_result.txt

# # Saving Result
# echo "## Pushing Result To DB"
# python3 -m scripts.push2db \
# 	--input_path buffer/${BASENAME}/final_result.pkl

