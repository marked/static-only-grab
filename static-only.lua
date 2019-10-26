dofile("table_show.lua")

local item_type = os.getenv('item_type')
local item_value = os.getenv('item_value')
local item_dir = os.getenv('item_dir')
local warc_file_base = os.getenv('warc_file_base')
local todo_url_count = os.getenv('todo_url_count')

local done_url_count = 0
local abortgrab = false
local code_counts = { }
local error_time = 1

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

  if status_code ~= 200 and status_code ~= 302 and status_code ~= 403 then
    abortgrab = true
  end


  if status_code == 200 then
    error_time = 1
  end

  if status_code == 403 then
    os.execute("sleep " .. tonumber(error_time))
    error_time = error_time * 2
  end

  if abortgrab == true or error_time > 15*60 then
    io.stdout:write("ABORTING...\n")
    io.stdout:flush()
    return wget.actions.ABORT --  Wget will abort() and exit immediately
  end

  return wget.actions.NOTHING  -- Finish this URL
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
  if (code_counts[200] == tonumber(todo_url_count)) and code_counts[200] > 0 then
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
