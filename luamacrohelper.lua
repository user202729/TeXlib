-- global variable
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


-- ========================================================


local in_runlocal=false
local executing_runtoks=false   -- debug variable, 2 purposes
-- * avoid forgotten \endlocalcontrol
-- * print Lua traceback on error
luatexbase.add_to_callback("show_error_message", function()
	luatexbase.remove_from_callback("show_error_message", "luamacrohelper show error callback")
	if executing_runtoks then
		io.write("\n" .. debug.traceback() .. "\n")
	end
	if in_runlocal and status.lasterrorstring:find "Forbidden control sequence found" then
		io.write("\n[luamacrohelper predicted error] Content inside runlocal are not local.\n")
	end
	io.write("\n" .. status.lasterrorstring)
end, "luamacrohelper show error callback")

--[[
luatexbase.add_to_callback("show_error_context", function()
	luatexbase.remove_from_callback("show_error_context", "luamacrohelper show error callback")

	local context=status.lasterrorcontext
	if context:sub(-1)=="\n" then
		context=context:sub(1, -2)
	end
	if context:sub(1, 1)=="\n" then
		context=context:sub(2)
	end

	io.write(".\n" .. context)
	io.write(debug.traceback())
end, "luamacrohelper show error callback")
]]

--luatexbase.remove_from_callback("show_error_hook", "luamacrohelper show error callback")

-- value is either a token list or a function (that prints out a token list)
-- value must include an endlocalcontrol token.
-- function can optionally return something which will be returned by the outer function
function L.runpeek(value)
	assert(not executing_runtoks)
	executing_runtoks=true
	local result
	tex.runtoks(function()
		local t=token.get_next()
		assert(t.cmdname=="extension", "internal error")  -- the "internal \endlocalcontrol token"
		if type(value)=="table" then
			tex.sprint(value)
		else
			result=value()
		end
	end)
	executing_runtoks=false
	return result
end


L.runpeek{
	token.create("begingroup"),
	token.create("expandafter"),
	token.create("endgroup"),
	token.create("expandafter"),
	token.create("endlocalcontrol"),
	token.create("csname"),
	token.create("endcsname"),
}
L.nullcs=token.get_next()
assert(L.nullcs.tok==0x20000000)


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
			L.runpeek(function()
				tex.sprint{
					token.create("begingroup"),
					token.create("expandafter"),
					token.create("endgroup"),
					token.create("expandafter"),
					token.create("endlocalcontrol"),
					token.create("csname"),
				}
				tex.sprint(-2, csname)
				tex.sprint{ token.create("endcsname") }
			end)
			t=token.get_next()
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

local function E3_onelevel(E3, name)
	local function f(_, argspec)
		if argspec==nil then argspec="" end
		return T[name..":"..argspec]
	end
	return setmetatable({}, {__index=f, __call=f})
end

local E3=setmetatable({}, {
	__index=E3_onelevel,
	__call=function(E3, name, argspec)
		if argspec==nil then return E3_onelevel(name) end
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

-- commonly used tokens
local bgroup=L.bgroupT "{"
L.bgroup=bgroup
local egroup=L.egroupT "}"
L.egroup=egroup


local runlocal_delimiter=T.__luamacrohelper_runlocal_delimiter
L.runpeek{
	T.outer, T.def, runlocal_delimiter, bgroup, T.endlocalcontrol, egroup, T.endlocalcontrol,
}

-- run something (tl or function) that executes locally
-- function can optionally return something which will be returned by the outer function
function L.runlocal(value)
	local result
	assert(not in_runlocal)
	in_runlocal=true
	L.runpeek(function()
		if type(value)=="table" then
			tex.sprint(L.cat(value, {runlocal_delimiter}))
		else
			result=value()
			tex.sprint({runlocal_delimiter})
		end
	end)
	in_runlocal=false
	return result

	--[[
	if type(value)=="table" then
		executing_runtoks=true
		tex.runtoks(function() tex.sprint(value) end)
		executing_runtoks=false
	else
		local result
		executing_runtoks=true
		tex.runtoks(function()
			result=value()
		end)
		executing_runtoks=false
		return result
	end
	]]
end


local first_unseen_index=123456
local function_table=lua.get_functions_table()

local function unused_function_index()  -- idempotent as long as the environment does not change
	while function_table[first_unseen_index] do
		first_unseen_index=first_unseen_index+1
	end
	return first_unseen_index
end

function L.def(name, f, prefix)
	if type(name)=="string" then name=T[name] end
	local prefix_tl={}
	if prefix~=nil then
		for t, _ in pairs(prefix) do
			if not ({protected=1, long=1, outer=1})[t] then
				error("invalid prefix "..tostring(t))
			end
			prefix_tl[#prefix_tl+1]=T[t]
		end
	end

	local index=unused_function_index()
	function_table[index]=f
	L.runlocal(function()
		tex.sprint(L.cati(prefix_tl, {T.luadef, name}))
		tex.sprint(-2, index.." ")
	end)
end

function L.deftoken(f)
	local t=T["__" .. unused_function_index() .. "_luamacrohelper_token"]
	L.def(t, f)
	return t
end

function L.protected_def(name, f)
	L.def(name, f, {protected=1})
end

function L.protected_long_def(name, f)
	L.def(name, f, {protected=1, long=1})
end

function L.expandonce() -- https://tex.stackexchange.com/a/649627/250119
	--L.runlocal{L.expandafter}  -- abuse internal implementation details here ... (see below)

	--alternatively:
	token.put_next{bgroup, T.expandafter, egroup}
	token.scan_toks(false, true)
end

function L.futurelet(token_obj)  -- futurelet token_obj to the next token in the input stream.
	L.runlocal{T.futurelet, token_obj}  -- abuse internal implementation details here that there's exactly one internal \endlocalcontrol token after these tokens
end

function L.get_next() -- wrapper for token.get_next() but handles never seen control sequence correctly (i.e. return the control sequence, add to hash table)
	L.futurelet(T.__luamacrohelper_internal_token)
	return token.get_next()
end

function L.get_nexte() -- second result value is whether the obtained token is a notexpanded token. Does not always detect successfully
	local result=L.get_next()
	return result, T.__luamacrohelper_internal_token.cmdname~=result.cmdname
end

-- importantly this function allows the argument to be initially unbalanced as long as the result is balanced
function L.exp_o(...)  -- args should be some token lists
	token.put_next(cati(cati({T.expandafter, bgroup}, ...), {egroup}))
	L.expandonce()
	return token.scan_toks()
end

function L.exp_x(...)
	L.runpeek(cati(cati({T["exp_args:Nx"], T.endlocalcontrol, bgroup}, ...), {egroup}))
	return token.scan_toks()
end

-- convert a token list consist of detokenized characters to Lua string
function L.to_str(tl)
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

function L.is_token(token_obj)
	return type(token_obj)=="userdata" and token_obj.tok
end

function L.is_tl(tl)
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
	return L.to_str(L.detokenize(tl))
end

function L.meaning(token_obj)  -- return a token list of detokenized characters
	assert(L.is_token(token_obj))
	return L.exp_o{T.meaning, token_obj}
end
function L.meaning_str(token_obj)  -- return a Lua string
	assert(L.is_token(token_obj))
	return L.to_str(L.meaning(token_obj))
end

function L.stringify(token_obj)  -- return a token list of detokenized characters
	assert(L.is_token(token_obj))
	return L.exp_o{T.string, token_obj}
end
function L.stringify_str(token_obj)  -- return a Lua string
	assert(L.is_token(token_obj))
	return L.to_str(L.stringify(token_obj))
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
	local result=token.scan_toks()
	local t=token.get_next()
	assert(t.csname=="__luamacrohelper_tokenize_unbalanced_delimiter",
		"unbalanced token list provided in str")
	return result
end



end
return luamacrohelper
