if luamacrohelper then
	error("luamacrohelper global variable is already defined!")
end
luamacrohelper={}

do local L=luamacrohelper

local function assertf(condition, s, ...)
	if not condition then
		error(s:format(...))
	end
end

function L.slice(t, i, j)
	assert(type(t)=="table")
	if j==nil then j=#t end
	local result={}
	for k=i, j do result[k-i+1]=t[k] end
	return result
end
function L.appendto(result, a)
	assert(type(a)=="table")
	for i=1, #a do result[#result+1]=a[i] end
end

function L.cat(...)
	local result={}
	local args={...}
	for j=1, #args do
		L.appendto(result, args[j])
	end
	return result
end

function L.cati(result, ...)  -- slight optimization, reuse the first table
	local args={...}
	for j=1, #args do
		L.appendto(result, args[j])
	end
	return result
end
local cati=L.cati

function L.reverse(t)
	assert(type(t)=="table")
	local result={}
	for i=#t, 1, -1 do result[#result+1]=t[i] end
	return result
end

function L.tl_equal(a, b)
	if #a~=#b then return false end
	for i=1, #a do if a[i].tok~=b[i].tok then return false end end
	return true
end


--------------------------------------------------------------------------------------------


local in_runlocal=false
local executing_TeX_in_Lua=false   -- debug variable, 2 purposes
-- * avoid forgotten \endlocalcontrol
-- * print Lua traceback on error


-- callback to print Lua traceback when error happens in inner TeX loop.
local callback_name="luamacrohelper show error callback"
luatexbase.add_to_callback("show_error_message", function()
	luatexbase.remove_from_callback("show_error_message", callback_name)
	if executing_TeX_in_Lua then
		io.write("\n" .. debug.traceback() .. "\n")
	end
	if in_runlocal and status.lasterrorstring:find "Forbidden control sequence found" then
		io.write("\n[luamacrohelper predicted error] Content inside runlocal are not local.\n")
	end
	io.write("\n" .. status.lasterrorstring)
end, callback_name)


local function token_create_force(s)
	assert(type(s)=="string")
	local result=token.create(s)
	assert(result.csname==s)
	return result
end

local endlocalcontrol_executed

function L.runlocal(value)  -- some error-checking functionalities are missing.
	--print("======== before\n", debug.traceback(), "\n\n")
	assert(not executing_TeX_in_Lua)
	assert(not in_runlocal)
	executing_TeX_in_Lua=true
	in_runlocal=true
	local result
	endlocalcontrol_executed=false
	token.put_next(token_create_force "__luamacrohelper_endlocalcontrol")
	tex.runtoks(function()
		local t=token.get_next()
		assert(t.cmdname=="extension", "internal error")  -- the "internal \endlocalcontrol token"

		if type(value)=="table" or type(value)=="string" then
			tex.sprint(value)
		else
			result=value()
		end
	end)
	assert(endlocalcontrol_executed, "local code executed endlocalcontrol early!")
	executing_TeX_in_Lua=false
	--print("======== after")
	in_runlocal=false
	return result
end


local first_unseen_index=123456
local function_table=lua.get_functions_table()

local function unused_function_index()  -- idempotent as long as the environment does not change
	while function_table[first_unseen_index] do
		first_unseen_index=first_unseen_index+1
	end
	return first_unseen_index
end


function L.luadef(name, f, prefix)
	if type(name)~="string" and name.csname then name=name.csname end
	assert(type(name)=="string")

	local prefix_tl={}
	if prefix~=nil then
		for t, _ in pairs(prefix) do
			if not ({protected=1, long=1, outer=1})[t] then
				error("invalid prefix "..tostring(t))
			end
			prefix_tl[#prefix_tl+1]=token_create_force(t)
		end
	end

	local index=unused_function_index()
	function_table[index]=f
	L.runlocal(function()
		tex.sprint(L.cati(prefix_tl, {token_create_force "expandafter", token_create_force "luadef", token_create_force "csname"}))
		tex.sprint(-2, name)
		tex.sprint {token_create_force "endcsname"}
		tex.sprint(-2, index.." ")
	end)

	return token_create_force(name)
end

L.luadef("__luamacrohelper_mark_endlocalcontrol_executed", function()
	assert(not endlocalcontrol_executed)
	endlocalcontrol_executed=true
end)

function L.token_of(f, prefix)
	local t="__" .. unused_function_index() .. "_luamacrohelper_token"
	L.luadef(t, f, prefix)
	return t
end

function L.protected_luadef(name, f)
	L.luadef(name, f, {protected=1})
end

function L.protected_long_luadef(name, f)
	L.luadef(name, f, {protected=1, long=1})
end

function L.unwind_input_stack()  -- https://tex.stackexchange.com/a/640959/250119
	L.runlocal {}
end

function L.scan_toks(definer, expand)
	executing_TeX_in_Lua=true
	local result=token.scan_toks(definer, expand)
	executing_TeX_in_Lua=false
	L.unwind_input_stack()
	return result
end


-- commonly used tokens
local bgroup=token.create(string.byte "{", 1)
L.bgroup=bgroup
local egroup=token.create(string.byte "}", 2)
L.egroup=egroup

function L.expandonce() -- https://tex.stackexchange.com/a/649627/250119
	--L.runlocal{L.expandafter}  -- abuse internal implementation details here ... (see below)

	--alternatively:
	token.put_next{bgroup, token_create_force "expandafter", egroup}
	L.scan_toks(false, true)
end

function L.futurelet(token_obj)
	assert(L.is_token(token_obj))

	--L.runpeek{T.futurelet, token_obj, T.endlocalcontrol}

	token.put_next{bgroup, token_create_force "immediateassignment", token_create_force "futurelet", token_obj, egroup}
	L.scan_toks(false, true)
end





tex.runtoks(function()
	local content=([[
	\begingroup
		\def\F{
			\directlua{luamacrohelper.nullcs=token.get_next()}
		}
		\expandafter\F\csname\endcsname
	\endgroup
	]]):gsub("%s", "")  -- be careful, gsub returns 2 values
	tex.sprint(content)
end)
assert(L.nullcs.tok==0x20000000)

----[==[

local next_token
L.luadef("__luamacrohelper_raw_get_next_token", function()
	next_token=token.get_next()
end)
local raw_get_next_token=token_create_force "__luamacrohelper_raw_get_next_token"
assert(raw_get_next_token.csname=="__luamacrohelper_raw_get_next_token")

-- token.create safe wrapper
-- usage: T.expandafter, T["expandafter"], T("{"), T("{", 1),
-- T(string.byte "{", 1)
local T=setmetatable({}, {
	__index=function(T, csname)
		assertf(type(csname)=="string", "invalid csname value |%s|", csname)
		if csname=="" then return L.nullcs end
		local t=token.create(csname)
		if t.csname=="" then
			-- impossible control sequence
			L.runlocal(function()
				tex.sprint{
					token.create("begingroup"),
					token.create("expandafter"),
					raw_get_next_token,
					token.create("csname"),
				}
				tex.sprint(-2, csname)
				tex.sprint{
					token.create("endcsname"),
					token.create("endgroup"),
				}
			end)
			t=next_token
			assert(t.cmdname=="undefined_cs")  -- we don't accidentally define it as \relax
		end
		assert(t.csname==csname)
		return t
	end,
	__call=function(T, char, cat)
		if type(char)=="string" then
			assertf(utf8.len(char)==1, "string '%s' should have 1 character", s)
			char=utf8.codepoint(char)
		end
		return token.create(char, cat)  -- cat might be nil, token.create will use current catcode
	end,
})
L.T=T



-- value is either a token list or a function (that prints out a token list)
-- value must include an endlocalcontrol token.
-- function can optionally return something which will be returned by the outer function
function L.runpeek(value)
	assert(not executing_TeX_in_Lua)
	executing_TeX_in_Lua=true
	local result
	tex.runtoks(function()
		local t=token.get_next()
		assert(t.cmdname=="extension", "internal error")  -- the "internal \endlocalcontrol token"
		if type(value)=="table" then
			token.put_next(value)
		else
			result=value()
		end
	end)
	executing_TeX_in_Lua=false
	L.unwind_input_stack()
	return result
end

local function E3_onelevel(E3, name)
	assert(type(name)=="string")
	local function f(_, argspec)
		if argspec==nil then argspec="" end
		return T[name..":"..argspec]
	end
	return setmetatable({}, {__index=f, __call=f})
end

local E3=setmetatable({}, {
	__index=E3_onelevel,
	__call=function(E3, name, argspec)
		if argspec==nil then return E3_onelevel(E3, name) end
		return T[name..":"..argspec]
	end,
})
L.E3=E3


-- short hand for L.T by name.
L.bgroupT     =function(x) return L.T(x, 1) end
L.egroupT     =function(x) return L.T(x, 2) end
L.mathT       =function(x) return L.T(x, 3) end
L.alignmentT  =function(x) return L.T(x, 4) end
L.paramT      =function(x) return L.T(x, 6) end
L.superscriptT=function(x) return L.T(x, 7) end
L.subscriptT  =function(x) return L.T(x, 8) end
L.spaceT      =function(x) return L.T(x, 10) end
L.letterT     =function(x) return L.T(x, 11) end
L.otherT      =function(x) return L.T(x, 12) end
L.activeT     =function(x) return L.T(x, 13) end

-- verbose alias (expl3 naming scheme)
L.begin_groupT     =L.bgroupT
L.end_groupT       =L.egroupT
L.math_toggleT     =L.mathT
L.math_superscriptT=L.superscriptT
L.math_subscriptT  =L.subscriptT









function L.futureletafter(token_obj)
	L.runpeek{T.afterassignment, T.endlocalcontrol, T.futurelet, token_obj}
end

local internal_token=T.__luamacrohelper_internal_token

function L.get_next()
	L.futurelet(internal_token)
	return token.get_next()
end

function L.get_nexte()
	local result=L.get_next()
	return result, internal_token.cmdname~=result.cmdname
end

--[[
function L.do_nothing_with_next()
	-- the sole purpose of this function is to workaround https://tex.stackexchange.com/q/640922/250119
	-- in some case this might change the notexpanded-ness of the following token, unfortunately

	-- replaced with L.unwind_input_stack()

	L.futurelet(internal_token)
	local cmdname1=internal_token.cmdname
	L.futurelet(internal_token)
	if cmdname1~=internal_token.cmdname then
		token.put_next(T.noexpand)
		L.expandonce()
	end
end
--]]

-- importantly this function allows the argument to be initially unbalanced as long as the result is balanced
function L.exp_o(...)  -- args should be some token lists
	token.put_next(cati(cati({T.expandafter, bgroup}, ...), {egroup}))
	L.expandonce()
	return L.scan_toks()
end

function L.exp_oo(...)
	token.put_next(cati(cati({T.expandafter, T.expandafter, T.expandafter, bgroup}, ...), {egroup}))
	L.expandonce()
	L.expandonce()
	return L.scan_toks()
end


function L.exp_x(...)
	L.runpeek(cati(cati({T["exp_args:Nx"], T.endlocalcontrol, bgroup}, ...), {egroup}))
	return L.scan_toks()
end

function L.exp_e(...)
	token.put_next(cati(cati({T.expanded, bgroup, bgroup}, ...), {egroup, egroup}))
	L.expandonce()
	return L.scan_toks()
end


function L.tl_to_str(tl)
	for i, v in ipairs(tl) do
		assert(v.csname==nil)
		if v.cmdname=="spacer" then
			assert(v.mode==32)
			tl[i]=' '
		else
			assert(v.cmdname=="other_char")
			assert(v.mode~=32)
			tl[i]=utf8.char(v.mode)
		end
	end
	return table.concat(tl)
end

local space_token=spaceT' '

function L.str_to_tl(s)
	result=""
	for _, c in utf8.codes(s) do
		if c==32 then
			s=space_token
		else
			s=L.otherT(c)
		end
	end
	return result
end

function L.is_token(token_obj)
	return type(token_obj)=="userdata" and token_obj.tok
end

function L.is_tl(tl)
	if type(tl)~="table" then return false end
	for i, v in pairs(tl) do
		if type(i)~="number" or not L.is_token(v) then
			return false
		end
	end
	return true
end

function L.detokenize(tl)  -- return a token list of detokenized characters
	assert(L.is_tl(tl))
	return L.exp_o({T.detokenize, bgroup}, tl, {egroup})
end
function L.detokenize_str(tl)  -- return a Lua string
	assertf(L.is_tl(tl), "%s is not a tl", tl)
	return L.tl_to_str(L.detokenize(tl))
end

function L.meaning(token_obj)  -- return a token list of detokenized characters
	assert(L.is_token(token_obj))
	return L.exp_o{T.meaning, token_obj}
end
function L.meaning_str(token_obj)  -- return a Lua string
	assert(L.is_token(token_obj))
	return L.tl_to_str(L.meaning(token_obj))
end

function L.stringify(token_obj)  -- return a token list of detokenized characters
	assert(L.is_token(token_obj))
	return L.exp_o{T.string, token_obj}
end
function L.stringify_str(token_obj)  -- return a Lua string
	assert(L.is_token(token_obj))
	return L.tl_to_str(L.stringify(token_obj))
end


-- similar to token.get_macro but returns a token list instead of a string
function L.get_macro(token_obj)
	assert(L.is_token(token_obj))
	assert(type(token_obj.csname)=="string", "token should be control sequence or active character")
	assertf(({
		call=1, long_call=1, outer_call=1, long_outer_call=1,
	})[token_obj.cmdname],
	"token is not a macro, token=|%s|, meaning=|%s|", L.detokenize_str{token_obj}, L.meaning_str(token_obj))  -- check is not foolproof
	return L.exp_o{token_obj}
end

function L.set_macro(token_obj, tl)
	L.runlocal(cati({T.edef, token_obj, bgroup, T.unexpanded, bgroup},
		tl,
		{egroup, egroup}))
end

L.runlocal{T.outer, T.def, T.__luamacrohelper_tokenize_unbalanced_delimiter, L.otherT("?"), bgroup, egroup}


function L.tokenize(str)
	L.runpeek(function()
		tex.sprint{T["use:n"], bgroup, T.endlocalcontrol, bgroup}
		tex.sprint(str)
		tex.sprint{egroup, egroup, T.__luamacrohelper_tokenize_unbalanced_delimiter}
	end)
	local result=L.scan_toks()
	local t=token.get_next()
	assert(t.csname=="__luamacrohelper_tokenize_unbalanced_delimiter",
		"unbalanced token list provided in str")
	return result
end

local brace_argument_token=T.__luamacrohelper_brace_argument
L.runlocal{T.def, brace_argument_token, L.paramT "#", L.otherT "1", bgroup, bgroup, L.paramT "#", L.otherT "1", egroup, egroup}

function L.get_argument()
	token.put_next(brace_argument_token)
	L.expandonce()
	return L.scan_toks()
end


--]==]


end
return luamacrohelper
