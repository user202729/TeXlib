-- Lua implementation of tlserialize.

local L=require "luamacrohelper"

local preamble=(
[[{]] ..
[[\edef\F{\ifnum0=0\fi}]] ..
[[\expandafter\let\expandafter\G\csname char_generate:nn\endcsname]] ..
[[\escapechar=-1\edef\-{\string\ }]] ..
[[\def\C#1.#2{\G{#1}{"#2}}]] ..
[[\def\P#1.{##\G{#1}6}]] ..
[[\def\O#1.{\G{#1}{12}}]] ..
[[\def\A#1.{\expandafter\expandafter\expandafter\noexpand\G{#1}{13}}]] ..
[[\def\S#1{\expandafter\noexpand\csname #1\endcsname}]] ..
[[\edef\T{]]
)

local finale=[[}\expandafter}\T%]]

local alt_finale=[[}\expandafter}\csname __tlser_result:n\expandafter\endcsname\expandafter{\T}%]]

-- use test_tlserialize_generate_table.tex to generate this table...

local safecat, cssafe={}, {}
safecat[33]=12 safecat[34]=12 safecat[36]=3 safecat[38]=4 safecat[39]=12 safecat[40]=12 safecat[41]=12 safecat[42]=12 safecat[43]=12 safecat[44]=12 safecat[45]=12 safecat[46]=12 safecat[47]=12 safecat[48]=12 safecat[49]=12 safecat[50]=12 safecat[51]=12 safecat[52]=12 safecat[53]=12 safecat[54]=12 safecat[55]=12 safecat[56]=12 safecat[57]=12 safecat[59]=12 safecat[60]=12 safecat[61]=12 safecat[62]=12 safecat[63]=12 safecat[65]=11 safecat[66]=11 safecat[67]=11 safecat[68]=11 safecat[69]=11 safecat[70]=11 safecat[71]=11 safecat[72]=11 safecat[73]=11 safecat[74]=11 safecat[75]=11 safecat[76]=11 safecat[77]=11 safecat[78]=11 safecat[79]=11 safecat[80]=11 safecat[81]=11 safecat[82]=11 safecat[83]=11 safecat[84]=11 safecat[85]=11 safecat[86]=11 safecat[87]=11 safecat[88]=11 safecat[89]=11 safecat[90]=11 safecat[91]=12 safecat[93]=12 safecat[96]=12 safecat[97]=11 safecat[98]=11 safecat[99]=11 safecat[100]=11 safecat[101]=11 safecat[102]=11 safecat[103]=11 safecat[104]=11 safecat[105]=11
safecat[106]=11 safecat[107]=11 safecat[108]=11 safecat[109]=11 safecat[110]=11 safecat[111]=11 safecat[112]=11 safecat[113]=11 safecat[114]=11 safecat[115]=11 safecat[116]=11 safecat[117]=11 safecat[118]=11 safecat[119]=11 safecat[120]=11 safecat[121]=11 safecat[122]=11 safecat[124]=12 cssafe[95]=true cssafe[58]=true cssafe[64]=true cssafe[35]=true 

for k, _ in pairs(safecat) do cssafe[k]=true end


function tlserialize_unchecked(tl)
	local result={preamble}


	-- match the braces, find out which brace pairs can be safely included
	local left_stack={}  -- list of indices of pending {s
	local brace_safe={}
	for index, token_obj in ipairs(tl) do
		if L.is_bgroup(token_obj) then
			if L.get_charcode(token_obj)==string.byte "{" then
				left_stack[#left_stack+1]=index
			else
				left_stack[#left_stack+1]=-1
			end
		elseif L.is_egroup(token_obj) then
			assert(#left_stack>0, "weird, input tl is unbalanced")
			local left_index=left_stack[#left_stack]
			left_stack[#left_stack]=nil
			if left_index>=0 and L.get_charcode(token_obj)==string.byte "}" then
				brace_safe[left_index]=true
				brace_safe[index]=true
			end
		end
	end
	assert(#left_stack==0, "weird, input tl is unbalanced")


	for index, token_obj in ipairs(tl) do
		local cur
		if L.is_explicit_character(token_obj) then
			local cat=L.get_catcode(token_obj)
			local char=L.get_charcode(token_obj)
			if char>=0x80 then
				cur="\\detokenize{" .. utf8.char(char) .. "}"  -- TODO temporary hack
			elseif brace_safe[index] or cat==safecat[char] then
				cur=utf8.char(char)
			elseif cat==6 then
				cur='\\P' .. char .. '.'
			elseif cat==10 then
				if char==32 then
					cur='\\-'
				else
					cur='\\C' .. char .. '.A'
				end
			elseif cat==12 then
				cur='\\O' .. char .. '.'
			elseif cat==13 then
				cur='\\A' .. char .. '.'
			else
				cur=('\\C%d.%X'):format(char, cat)
			end
		else
			if L.token_equal(L.frozen_relax, token_obj) then
				cur='\\F'
			else
				result[#result+1]='\\S{'
				for _, c in utf8.codes(token_obj.csname) do
					if cssafe[c] then
						result[#result+1]=utf8.char(c)
					else
						result[#result+1]='\\O' .. c .. '.'
					end
				end
				cur='}'
			end
		end
		result[#result+1]=cur
	end
	result[#result+1]=finale
	return table.concat(result)
end

local result_tl
L.protected_long_luadef("__tlser_result:n", function()
	result_tl=L.get_argument_braced()
end)

L.protected_long_luadef("tlserialize_unchecked:Nn", function()
	local target=L.get_argument_unbraced()
	local tl=L.get_argument_braced()
	L.set_macro(target, L.str_to_strtl(tlserialize_unchecked(tl)))
end)

function tldeserialize(s)
	if #s>#finale and s:sub(-#finale)==finale then
		result_tl=nil
		L.runlocal(s:sub(0, -#finale-1) .. alt_finale)
		assert(result_tl~=nil)
		return result_tl
	else
		error("Token list cannot be deserialized")
	end
end

L.protected_long_luadef("tldeserialize:Nn", function()
	local target=L.get_argument_unbraced()
	local tl=L.get_argument_braced()
	L.set_macro(target, tldeserialize(L.strtl_to_str(tl)))
end)

function tlserialize_optional(tl)
	local s=tlserialize_unchecked(tl)
	return s, L.tl_equal(tl, tldeserialize(s))
end

function tlserialize(tl)
	local s, success=tlserialize_optional(tl)
	assert(success)
	return s
end

L.protected_long_luadef("tlserialize:NnTF", function()
	local target=L.get_argument_unbraced()
	local tl=L.get_argument_braced()
	local true_branch=L.get_argument_braced()
	local false_branch=L.get_argument_braced()

	local s, success=tlserialize_optional(tl)
	L.set_macro(target, L.str_to_strtl(s))

	if success then token.put_next(true_branch) else token.put_next(false_branch) end
end)
