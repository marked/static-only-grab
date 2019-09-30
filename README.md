# yourshot-static-grab
Parses JSON API, grabs URLs (images or html)

Example

wget-lua -nv -O output.bin --truncate --lua-script yourshot-static.lua --warc-file 2019-01-01 'https://yourshot.nationalgeographic.com/api/v3/photos/search/?start_date=2019-01-01&end_date=2019-01-01&sort_by=-publication_date' 

OR

run-pipeline pipeline.py $USERNAME

TODO: add check that wget got the same # of URLs as python sent
