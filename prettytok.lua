do
local function looks_like_token(t)
	return type(t)=="userdata" or (type(t)=="table" and t.cmdname~=nil and t.tok~=nil)
end

-- public API :: once the package is loaded, this holds the .tok value of the frozen relax token
prettyprint_frozenrelaxtok=nil

local function prettyprint_term_one_arg(tokenlist)

	if looks_like_token(tokenlist) then
		return prettyprint_term_one_arg({tokenlist})
	end

	---- result variable here
	local s=""

	---- color

	--[[
	local gray  ='\x1b[90m'
	local red   ='\x1b[31m'
	local green ='\x1b[38;5;121m'
	local yellow='\x1b[93m'
	local white ='\x1b[0m'
	]]

	local gray  =token.get_macro "_prettytok_gray"
	local red   =token.get_macro "_prettytok_red"
	local green =token.get_macro "_prettytok_green"
	local yellow=token.get_macro "_prettytok_yellow"
	local white =token.get_macro "_prettytok_white"
	local prettytermprefixmore=token.get_macro "prettytermprefixmore"


	local color=white  -- the current color
	local function set_color(c)
		if color~=c then
			color=c
			s=s..c
		end
	end


	local function print_term_char(code)
		if code<27 then
			if code==9 then
				s=s.."⇥"
			else
				s=s.."^^"..string.char(code+64)
				if code==13 or code==10 then
					s=s.."\n"..prettytermprefixmore
				end
			end
		elseif code==32 then
			s=s.."␣"
		else
			s=s..utf8.char(code)
		end
	end


	local function printstring(t)
		-- this is just for debugging/convenience purpose. If the item is a string instead of a token...
		t=tostring(t)
		for _, c in utf8.codes(t) do
			if c==32 then
				set_color(gray)
				s=s.."␣"
			else
				set_color(white)
				s=s..utf8.char(c)
			end
		end
	end

	if type(tokenlist)~="table" then
		-- user give a string (or something similar). Print it as detokenized characters
		printstring(tokenlist)
	
	else

		-- normal print of tokenlist
		for i=1, #tokenlist do
			local t=tokenlist[i]
			if not looks_like_token(t) then
				printstring(t)
			elseif t.csname==nil then
				set_color(({left_brace=red, right_brace=red, math_shift=red, tab_mark=red, mac_param=red, sup_mark=red, sub_mark=red, spacer=gray, letter=green, other_char=white})[t.cmdname])
				print_term_char(t.mode)
			else
				if t.active then
					set_color(yellow)
					print_term_char(utf8.codepoint(t.csname))
				elseif t.tok==prettyprint_frozenrelaxtok then
					set_color(red)
					s=s.."\\relax "
				else
					set_color(yellow)
					s=s.."\\"
					for _, c in utf8.codes(t.csname) do
						print_term_char(c)
					end
					s=s.." "
				end
			end
		end
		
	end

	set_color(white)
	return s
end

local function prettyprint_one_arg(tokenlist)

	if looks_like_token(tokenlist) then
		return prettyprint_one_arg({tokenlist})
	end

	local s=""

	local function printstring(t)
		-- this is just for debugging/convenience purpose. If the item is a string instead of a token...
		t=tostring(t)
		for _, c in utf8.codes(t) do
			if c==32 then
				s=s.."token("..c..',"A"),'
			else
				s=s.."token("..c..',"C"),'
			end
		end
	end

	if type(tokenlist)~="table" then
		-- user give a string (or something similar). Print it as detokenized characters
		printstring(tokenlist)
	
	else

		-- normal print of tokenlist
		for i=1, #tokenlist do
			local t=tokenlist[i]
			if not looks_like_token(t) then
				printstring(t)
			elseif t.csname==nil then
				s=s.."token("..t.mode..',"'..(({left_brace=1, right_brace=2, math_shift=3, tab_mark=4, mac_param=6, sup_mark=7, sub_mark=8, spacer="A", letter="B", other_char="C"})[t.cmdname])..'"),'
			else
				if t.active then
					s=s.."token("..utf8.codepoint(t.csname)..',"D"),'
				elseif t.tok==prettyprint_frozenrelaxtok then
					s=s.."csfrozenrelax(),"
				else
					s=s.."cs("
					-- TODO
					for _, c in utf8.codes(t.csname) do
						s=s..c..","
					end
					s=s.."),"
				end
			end
		end
		
	end
	return s
end

local function get_output_format()
	return token.get_macro "_prettytok_output_format"
end

local function get_file_number()
	return token.get_mode(token.create("_prettytok_file"))
end

local function error_uninitialized()
	error "Must initialize before using Lua prettyprint functions"
end

local function check_initialized()
	if get_output_format()=="" then
		error_uninitialized()
	end
end

function prettyprint(...)
	local output_format=get_output_format()
	local args={...}
	if output_format=="html" then
		local prettyfilenumber=get_file_number()

		local s="print_tl("
		for i=1, select("#", ...) do
			s=s..prettyprint_one_arg(args[i])
		end

		texio.write(prettyfilenumber, s..")//</script><script>\n")
	elseif output_format=="term" then
		local s=token.get_macro "prettytermprefix"
		for i=1, select("#", ...) do
			s=s..prettyprint_term_one_arg(args[i])
		end
		texio.write_nl("")
		print(s)
	else
		error_uninitialized()
	end
end

function prettyprintw()
	check_initialized()
	local extra=token.scan_toks()
	local s={}
	local last_token
	while true do
		last_token=token.get_next()
		if last_token.csname=="prettystop" then break end
		s[#s+1]=last_token
	end

	prettyprint(extra, s)  -- exclude the \prettystop token
	s[#s+1]=last_token
	token.put_next(s)
end
end
