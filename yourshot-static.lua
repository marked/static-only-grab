dofile("table_show.lua")

local item_type = os.getenv('item_type')
local item_value = os.getenv('item_value')
local item_dir = os.getenv('item_dir')
local warc_file_base = os.getenv('warc_file_base')
local todo_url_count = os.getenv('todo_url_count')

local done_url_count = 0
local abortgrab = false
local code_counts = { }

json_lib = require "json"
host = "https://yourshot.nationalgeographic.com"

------------------------------------------------------------------------------------------------

wget.callbacks.get_urls = function(file, url, is_css, iri)
  local next_urls = { }

  if string.match(url, host .. "/api") then  -- expect JSON
    local resp_fh = assert(io.open(file))
    local resp_json = resp_fh:read('*all')
    resp_fh:close()

    results = json_lib.decode(resp_json)["results"]

    for result_index, result_body in pairs(results) do
      local frame_path = result_body["detail_url"]
      io.stdout:write(result_index, frame_path)
      io.stdout:flush()
      table.insert(next_urls,
        {
          url = host .. frame_path,
          link_expect_html = 1,
          link_expect_css = 0
        }
      )

      for img_res, img_path in pairs(result_body["thumbnails"]) do
        print(img_res, img_path)
        table.insert(next_urls,
          {
            url = host .. img_path,
            link_expect_html = 0,
            link_expect_css = 0
          }
        )
      end  -- for thumbnails
    end  -- for results
  end -- if JSON

  return next_urls
end

------------------------------------------------------------------------------------------------

wget.callbacks.httploop_result = function(url, err, http_stat)
  status_code = http_stat["statcode"]

  done_url_count = done_url_count + 1
  io.stdout:write(done_url_count .. "=" .. status_code .. " " .. url["url"] .. "  \n")
  io.stdout:flush()

  if code_counts[status_code] == nil then
    code_counts[status_code] = 1
  else
    code_counts[status_code] = 1 + code_counts[status_code]
  end

  if status_code ~= 200 then
    abortgrab = true
  end

  if abortgrab == true then
    io.stdout:write("ABORTING...\n")
    io.stdout:flush()
    return wget.actions.ABORT --  Wget will abort() and exit immediately
  end

  return wget.actions.EXIT  -- Finish this URL
end

------------------------------------------------------------------------------------------------

wget.callbacks.before_exit = function(exit_status, exit_status_string)
  io.stdout:write(table.show(code_counts,'\nResponse Code Frequency'))
  io.stdout:write("Received: " .. exit_status .. exit_status_string .. "\n")
  io.stdout:flush()

  if abortgrab == true then
    io.stdout:write("Abort/Sending: " .. "wget.exits.IO_FAIL\n\n")
    return wget.exits.IO_FAIL
  end
  if code_counts[200] == todo_url_count and table.count(code_counts) == 1 and todo_url_count > 0 then
    io.stdout:write("Sending: " .. "wget.exits.SUCCESS\n\n")
    return wget.exits.SUCCESS
  else
    io.stdout:write("Sending: " .. "wget.exits.NETWORK_FAIL\n\n")
    return wget.exits.NETWORK_FAIL
  end

  io.stdout:write("Sending: " .. "wget.exits.UNKNOWN\n\n")
  return wget.exits.UNKNOWN
end

------------------------------------------------------------------------------------------------
