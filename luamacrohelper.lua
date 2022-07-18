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
local appendto=L.appendto

function L.cat(...)
	local result={}
	local args={...}
	for j=1, #args do
		L.appendto(result, args[j])
	end
	return result
end
local cat=L.cat

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

function L.token_equal(a, b)
	return a.tok==b.tok
end

--------------------------------------------------------------------------------------------


--local in_runlocal=false  -- used to check that runlocal is not nested

local executing_TeX_in_Lua=0   -- debug variable, 2 purposes
-- * avoid forgotten \endlocalcontrol
-- * print Lua traceback on error


-- callback to print Lua traceback when error happens in inner TeX loop.
local callback_name="luamacrohelper show error callback"
luatexbase.add_to_callback("show_error_message", function()
	luatexbase.remove_from_callback("show_error_message", callback_name)
	if executing_TeX_in_Lua>0 then
		io.write("\n" .. debug.traceback() .. "\n")
	end
	--if in_runlocal and status.lasterrorstring:find "Forbidden control sequence found" then
	--	io.write("\n[luamacrohelper predicted error] Content inside runlocal are not local.\n")
	--end
	io.write("\n" .. status.lasterrorstring)
end, callback_name)


local function token_create_force(s)
	assert(type(s)=="string")
	local result=token.create(s)
	assert(result.csname==s)
	return result
end

local endlocalcontrol_executed

function L.runlocal_internal(value)
	executing_TeX_in_Lua=executing_TeX_in_Lua+1
	local result

	local old_endlocalcontrol_executed=endlocalcontrol_executed  -- since it's nest-able!

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

	endlocalcontrol_executed=old_endlocalcontrol_executed

	executing_TeX_in_Lua=executing_TeX_in_Lua-1
end


function L.runlocal(value)  -- some error-checking functionalities are missing.
	--print("======== before\n", debug.traceback(), "\n\n")

	--assert(not in_runlocal, "runlocal cannot be nested")
	--in_runlocal=true

	L.runlocal_internal(value)

	--in_runlocal=false
	return result
end


local function_table=lua.get_functions_table()
local first_unseen_index=1


local function unused_function_index()  -- not guaranteed to be idempotent because of Lua 5.2...
	-- https://tex.stackexchange.com/questions/632408/how-can-i-exclude-tex-macros-when-counting-a-strings-characters-in-lua/632464?noredirect=1#comment1623008_632464 maybe it should be allocated sequentially
	local l=#function_table+1
	if type(l)=="number" and function_table[l]==nil and math.floor(l)==l and 0<l and l<10000000 then  -- just in case it's Lua 5.2 https://stackoverflow.com/q/23590885
		first_unseen_index=l
	else
		while function_table[first_unseen_index] do
			first_unseen_index=first_unseen_index+1
		end
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

	if name==nil then
		name="__" .. index .. "_luamacrohelper_token"
	end

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
	return L.luadef(nil, f, prefix)
end

function L.protected_luadef(name, f)
	L.luadef(name, f, {protected=1})
end

function L.protected_long_luadef(name, f)
	L.luadef(name, f, {protected=1, long=1})
end

function L.unwind_input_stack()  -- https://tex.stackexchange.com/a/640959/250119
	L.runlocal_internal {}
end

local internal_scan_toks=token.scan_toks

function L.scan_toks_no_unwind(definer, expand)
	executing_TeX_in_Lua=executing_TeX_in_Lua+1
	local result=internal_scan_toks(definer, expand)
	executing_TeX_in_Lua=executing_TeX_in_Lua-1
	return result
end

function L.scan_toks(definer, expand)
	local result=L.scan_toks_no_unwind(definer, expand)
	L.unwind_input_stack()
	return result
end

-- commonly used tokens
local bgroup=token.create(string.byte "{", 1)
L.bgroup=bgroup
local egroup=token.create(string.byte "}", 2)
L.egroup=egroup
local space=token.create(string.byte " ", 10)
L.space=space
local param=token.create(string.byte "#", 6)
L.param=param

function L.expandonce() -- https://tex.stackexchange.com/a/649627/250119
	--L.runlocal{L.expandafter}  -- abuse internal implementation details here ... (see below)

	--alternatively:
	token.put_next{bgroup, token_create_force "expandafter", egroup}
	internal_scan_toks(false, true)
end

function L.futurelet(token_obj)
	assert(L.is_token(token_obj))

	--L.runpeek{T.futurelet, token_obj, T.endlocalcontrol}

	token.put_next{bgroup, token_create_force "immediateassignment", token_create_force "futurelet", token_obj, egroup}
	internal_scan_toks(false, true)
end






----[==[

local next_token
local raw_get_next_token=L.luadef("__luamacrohelper_raw_get_next_token", function()
	next_token=token.get_next()
end)

local function create_new_cs(csname)  -- using \csname ... \endcsname. Wrap in a group to avoid accidentally defining it as \relax.
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
	return next_token
end

L.nullcs=create_new_cs ""
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
			t=create_new_cs(csname)
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

function L.Tprefixed(prefix)
	assert(type(prefix)=="string")
	return setmetatable({}, {
		__index=function(_, csname)
			return T[prefix..csname]
		end,
		__call=function(_, csname)
			return prefix..csname
		end,
	})
end

local Tprivate=L.Tprefixed "__luamacrohelper_"


-- value is either a token list or a function (that prints out a token list)
-- value must include an endlocalcontrol token.
-- function can optionally return something which will be returned by the outer function
function L.runpeek(value)
	--assert(not in_runlocal)
	--in_runlocal=true

	executing_TeX_in_Lua=executing_TeX_in_Lua+1
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
	executing_TeX_in_Lua=executing_TeX_in_Lua-1
	L.unwind_input_stack()

	--in_runlocal=false
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


function L.is_explicit_character(token_obj)
	--gives wrong result with some certain internal tokens such as the internal \endlocalcontrol
	return token_obj.active or token_obj.csname==nil
end

local catcode_from_cmdname_lookup={}

for _, value in pairs {
	{"left_brace" ,{"begin_group"     , "bgroup"     }, 1 },
	{"right_brace",{"end_group"       , "egroup"     }, 2 },
	{"math_shift" ,{"math_toggle"     , "math"       }, 3 },
	{"tab_mark"   ,{"alignment"       ,              }, 4 },
	{"mac_param"  ,{"parameter"       , "param"      }, 6 },
	{"sup_mark"   ,{"math_superscript", "superscript"}, 7 },
	{"sub_mark"   ,{"math_subscript"  , "subscript"  }, 8 },
	{"spacer"     ,{"space"           ,              }, 10},
	{"letter"     ,{"letter"          ,              }, 11},
	{"other_char" ,{"other"           ,              }, 12},
	{false        ,{"active"          ,              }, 13},
} do
	local cmdname, names, cat=table.unpack(value)
	catcode_from_cmdname_lookup[cmdname]=cat
	for _, name in pairs(names) do
		L[name.."T"] = function(x) return L.T(x, cat) end
		L["thecat_" .. name] = cat
		if cmdname~=nil then
			L["is_"..name] = function(x) return x.csname==nil and x.cmdname==cmdname end
		end
	end
end

function L.is_active(x) return x.active end

function L.get_catcode(x)
	assert(L.is_explicit_character(x))
	if x.active then return 13 end
	return catcode_from_cmdname_lookup[x.cmdname]
end

function L.get_charcode(x)
	assert(L.is_explicit_character(x))
	if x.active then
		assertf(utf8.len(x.csname)==1, "internal error?")
		return utf8.codepoint(x.csname)
	end
	return x.mode
end

function L.futureletafter(token_obj)
	L.runpeek{T.afterassignment, T.endlocalcontrol, T.futurelet, token_obj}
end

local internal_token=Tprivate.internal_token

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

local space_token=L.spaceT " "

function L.str_to_tl(s)
	result={}
	for _, c in utf8.codes(s) do
		if c==32 then
			result[#result+1]=space_token
		else
			result[#result+1]=L.otherT(c)
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

L.runlocal{T.outer, T.def, Tprivate.tokenize_unbalanced_delimiter, L.otherT("?"), bgroup, egroup}


function L.tokenize(str, setup)
	L.runpeek(function()
		tex.sprint {T.begingroup}
		if setup~=nil then
			if type(setup)=="string" then
				assert(nil==setup:match "\n")
			else
				assertf(L.is_tl(setup), "%s is neither string nor tl", setup)
			end
			tex.sprint(setup)
		end
		tex.sprint{T["use:n"], bgroup, T.endgroup, T.endlocalcontrol, bgroup}

		-- print out the content of the string as multiple lines
		local last_line=nil
		for line in str:gmatch "[^\n]*" do
			if last_line~=nil then
				tex.print(last_line)
			end
			last_line=line
		end
		if #last_line>0 then tex.sprint(last_line) end

		tex.sprint{egroup, egroup, Tprivate.tokenize_unbalanced_delimiter}
	end)
	local result=L.scan_toks()
	local t=token.get_next()
	assert(t.csname==Tprivate "tokenize_unbalanced_delimiter",
		"unbalanced token list provided in str")
	return result
end

local make_braces_other=L.token_of(function()
	assert(tex.catcode[string.byte "{"]==L.thecat_bgroup)
	assert(tex.catcode[string.byte "}"]==L.thecat_egroup)
	tex.catcode[string.byte "{"]=L.thecat_other
	tex.catcode[string.byte "}"]=L.thecat_other
end)

function L.tokenize_unbalanced_braces(str, setup)
	-- same as above.
	-- the tokens `{` and `}` might be unbalanced.
	-- setup must be a table, for simplicity...
	local result=L.tokenize(str, cat(setup, {make_braces_other}))
	for i, v in pairs(result) do
		if L.is_other(v) then
			local char=L.get_charcode(v)
			if char==string.byte "{" then
				result[i]=bgroup
			elseif char==string.byte "}" then
				result[i]=egroup
			end
		end
	end
	return result
end

local brace_argument_token=Tprivate.brace_argument
L.runlocal{T.def, brace_argument_token, param, L.otherT "1", bgroup, bgroup, param, L.otherT "1", egroup, egroup}

function L.get_argument()
	token.put_next(brace_argument_token)
	L.expandonce()
	return L.scan_toks()
end

function L.get_argumente()
	local t=L.get_next()
	if t.tok==space.tok then return L.get_argumente() end
	if t.csname==nil and t.cmdname=="left_brace" then
		token.put_next(t)
		return L.scan_toks(), true
	else
		return {t}, false
	end
end

function L.get_argument_braced()
	local result, braced=L.get_argumente()
	assert(braced, "argument is not braced!")
	return result
end

function L.get_argument_unbraced()
	local result, braced=L.get_argumente()
	assert(not braced, "argument is braced!")
	assert(#result==1)
	return result[1]
end

function L.expl_tokenize_unbalanced_braces(s)
	return L.tokenize_unbalanced_braces(s, {E3.cctab_select.N, T.c_code_cctab})
end

function L.doc_tokenize_unbalanced_braces(s)
	return L.tokenize_unbalanced_braces(s, {E3.cctab_select.N, T.c_document_cctab})
end


function L.expl_tl(...)
	local args={...}
	if select("#", ...)~=#args then
		error("some argument value is nil")
	end
	local result={}
	for _, v in ipairs(arg) do
		if type(v)=="string" then
			appendto(result, L.expl_tokenize(v))
		elseif type(v)=="table" then
			appendto(result, v)
		else
			result[#result+1]=v
		end
	end
	assert(L.is_tl(result))
	return result
end

L.runlocal(cati({T.expandafter, raw_get_next_token, T.ifnum}, L.str_to_tl "0=0", {T.fi}))
L.frozen_relax=next_token
assert(L.frozen_relax.csname=="relax")

--]==]


end
return luamacrohelper
