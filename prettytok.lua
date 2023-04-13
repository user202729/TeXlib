do
local function looks_like_token(t)
	return type(t)=="userdata" or (type(t)=="table" and t.cmdname~=nil and t.tok~=nil)
end

-- public API :: once the package is loaded, this holds the .tok value of the frozen relax token
prettyprint_frozenrelaxtok=nil


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
	return token.get_macro "_prettytok_mode"
end

local function get_file_number()
	return token.get_mode(token.create("_prettytok_file"))
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
	else
		assert(output_format=="term-8bit" or output_format=="term-shell")
		texio.write_nl("")

		local content=""
		local content_len=0  -- only count visible content

		local function typeout_content()
			print(content)
			content=""
			content_len=0
		end

		local function append_content(s)  -- only call this on content that takes visible width. For example don't use this to set color
			assert(type(s)=="string")
			content=content..s
			content_len=content_len+utf8.len(s)
		end

		append_content(token.get_macro "prettytermprefix")
		local wraplimit=tonumber(token.get_macro "prettytermwraplimit")

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

		local current_color=white
		local function setcolor(c)
			if current_color~=c then
				current_color=c
				content=content..c
			end
		end

		local prettytermprefixmore=token.get_macro "prettytermprefixmore"

		local function check_wrap()
			if content_len>wraplimit then
				if current_color~=white then
					content=content..white
				end
				print(content)
				
				content=""
				content_len=0
				append_content(prettytermprefixmore)
				if current_color~=white then
					content=content..current_color
				end
			end
		end

		local function prettyprint_term_one_arg(tokenlist)
			if looks_like_token(tokenlist) then
				return prettyprint_term_one_arg({tokenlist})
			end


			local function print_term_char(code)
				if code<27 then
					if code==9 then
						append_content("⇥")
					else
						append_content("^^"..string.char(code+64))
						if code==13 or code==10 then
							typeout_content()
							append_content(prettytermprefixmore)  -- color the prefix with the same color
						end
					end
				elseif code==32 then
					append_content("␣")
				else
					append_content(utf8.char(code))  -- unlike TeX implementation currently this does not show ^^⟨hex digits⟩ representation
				end
			end


			local function printstring(t)
				-- this is just for debugging/convenience purpose. If the item is a string instead of a token...
				t=tostring(t)
				for _, c in utf8.codes(t) do
					if c==32 then
						setcolor(gray)
						append_content("␣")
					else
						setcolor(white)
						append_content(utf8.char(c))
					end
				end
			end

			if type(tokenlist)~="table" then
				-- user give a string (or something similar). Print it as detokenized characters
				printstring(tokenlist)
				check_wrap()
			
			else

				-- normal print of tokenlist
				for i=1, #tokenlist do
					local t=tokenlist[i]
					if not looks_like_token(t) then
						printstring(t)
						check_wrap()
					elseif t.csname==nil then
						setcolor(({left_brace=red, right_brace=red, math_shift=red, tab_mark=red, mac_param=red, sup_mark=red, sub_mark=red, spacer=gray, letter=green, other_char=white})[t.cmdname])
						print_term_char(t.mode)
						check_wrap()
					else
						if t.active then
							setcolor(yellow)
							print_term_char(utf8.codepoint(t.csname))
						elseif t.tok==prettyprint_frozenrelaxtok then
							setcolor(red)
							append_content("\\relax ")
						else
							setcolor(yellow)
							append_content("\\")
							for _, c in utf8.codes(t.csname) do
								print_term_char(c)
							end
							append_content(" ")
						end
						check_wrap()
					end
				end
				
			end
		end

		for i=1, select("#", ...) do
			prettyprint_term_one_arg(args[i])
		end

		setcolor(white)

		typeout_content()
	end
end

function prettyprintw()
	local callback=token.scan_toks()
	local extra=token.scan_toks()
	local s={}
	local last_token
	while true do
		last_token=token.get_next()
		if last_token.csname=="prettystop" then break end
		s[#s+1]=last_token
		callback[#callback+1]=last_token
	end

	prettyprint(extra, s)  -- exclude the \prettystop token
	callback[#callback+1]=last_token
	token.put_next(callback)
end
end
