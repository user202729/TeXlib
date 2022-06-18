do
local function looks_like_token(t)
	return type(t)=="userdata" or (type(t)=="table" and t.cmdname~=nil and t.tok~=nil)
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
				else
					s=s.."cs("
					for j=1, #t.csname do
						s=s..t.csname:byte(j)..","
					end
					s=s.."),"
				end
			end
		end
		
	end
	return s
end

function prettyprint(...)
	if token.get_macro("prettypreamble") ~= nil then
		error("pretty file not initialized!")
	end
	local prettyfilenumber=token.get_mode(token.create("__prettyh_file"))
	local s="print_tl("

	local args={...}
	for i=1, select("#", ...) do
		s=s..prettyprint_one_arg(args[i])
	end

	texio.write(prettyfilenumber, s..")//</script><script>\n")
end
end
