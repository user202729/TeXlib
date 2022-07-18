-- Lua implementation of tlserialize.

local L=require "luamacrohelper"

local preamble=(
[[{]] ..
[[\edef\F{\ifnum0=0\fi}]] ..
[[\expandafter\let\expandafter\GGG\csname char_generate:nn\endcsname]] ..
[[\escapechar=-1\edef\-{\string\ }]] ..
[[\def\C#1.#2{\GGG{#1}{"#2}}]] ..
[[\def\P#1.{##\GGG{#1}6}]] ..
[[\def\O#1.{\GGG{#1}{12}}]] ..
[[\def\A#1.{\expandafter\expandafter\expandafter\noexpand\GGG{#1}{13}}]] ..
[[\def\S#1{\expandafter\noexpand\csname #1\endcsname}]] ..
[[\edef\T{]]
)

local finale=[[}\expandafter}\T%]]

local alt_finale=[[}\expandafter}\csname __tlser_result:n\expandafter\endcsname\expandafter{\T}%]]

function tlserialize_unchecked(tl)
	local result={preamble}
	for _, token_obj in ipairs(tl) do
		local cur
		if L.is_explicit_character(token_obj) then
			local cat=L.get_catcode(token_obj)
			local char=L.get_charcode(token_obj)
			if cat==6 then
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
					result[#result+1]='\\O' .. c .. '.'
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
	L.set_macro(target, L.str_to_tl(tlserialize_unchecked(tl)))
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
	L.set_macro(target, tldeserialize(L.tl_to_str(tl)))
end)

function tlserialize(tl)
	local s=tlserialize_unchecked(tl)
	return s, L.tl_equal(tl, tldeserialize(s))
end

L.protected_long_luadef("tlserialize:NnTF", function()
	local target=L.get_argument_unbraced()
	local tl=L.get_argument_braced()
	local true_branch=L.get_argument_braced()
	local false_branch=L.get_argument_braced()

	local s, success=tlserialize(tl)
	L.set_macro(target, L.str_to_tl(s))

	if success then token.put_next(true_branch) else token.put_next(false_branch) end
end)
