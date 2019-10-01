# yourshot-static-grab
Parses JSON API, grabs URLs (images or non-recursive html), exports other assets to text files

Example

wget-lua -nv -O output.bin --truncate --lua-script yourshot-static.lua --warc-file 2019-01-01 'https://yourshot.nationalgeographic.com/api/v3/photos/search/?start_date=2019-01-01&end_date=2019-01-01&sort_by=-publication_date' 

OR

run-pipeline pipeline.py $USERNAME

Also: https://github.com/marked/yourshot-static-items
