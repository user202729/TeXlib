do

	
---[==[

local L=require "luamacrohelper"
local T=L.T
function ignore() end

--test for T.
ignore(T[""])
ignore(T.expandafter)
ignore(T.neverseenbefore)
ignore(T.neverseenbeforea)
ignore(T.neverseenbeforeb)
-- already include assertions


local bgroup=L.bgroup
local egroup=L.egroup
local E3=L.E3



-- need to repeat 6000 times to test https://tex.stackexchange.com/q/640922/250119

-- simple case, if it peeks forward then bug does not happen
token.put_next {bgroup, T.relax, egroup}
for i=1, 6000 do
	L.runpeek {E3.exp_args.No, T.endlocalcontrol}
end
assert(L.tl_equal(token.scan_toks(), {T.relax}))

-- if it leaves some extra tokens, they should be preserved
for i=1, 6000 do
	L.runpeek {T.endlocalcontrol, T.weird}
	local t=token.get_next()
	L.unwind_input_stack()
	assert(t.csname=="weird")
end

-- if it does not peek forward bug should still not happen
for i=1, 6000 do
	L.runpeek {T.def, T.__test, bgroup, egroup, T.endlocalcontrol}
end

-- test runlocal
for i=1, 6000 do
	L.runlocal({T.def, T.__test, bgroup, egroup})
end

-- test T
for i=1, 6000 do
	ignore(T["neverseen-" .. i])
end


-- test L.get_next()
L.luadef("fff", function()
	assert(token.get_next().csname=="")
	assert(token.get_next().csname=="")  -- which will not actually get the token
	assert(L.get_next().csname=="anotherneverseen")
	assert(token.get_next().csname=="anotherneverseen")
	assert(token.get_next().csname=="def")
end)


L.set_macro(T.abc, {T.x, T.y})
for i=1, 6000 do
	assert(L.detokenize_str{T.abc, T.def} == [[\abc \def ]])
end
assert(L.detokenize_str{T.abc} == [[\abc ]])
assert(L.stringify_str (T.abc) == [[\abc]])
assert(L.tl_equal(L.get_macro(T.abc), {T.x, T.y}))

assert(L.meaning_str(L.bgroupT "A") == "begin-group character A")
assert(L.meaning_str(L.egroupT "B") == "end-group character B")
assert(L.stringify_str(L.egroupT "B") == "B")



--[[ test error message
L.runlocal{
	T.def, bgroup, egroup,
}

L.runlocal {T["use:n"]}

L.runlocal {T.endlocalcontrol}

--]]


local E3=L.E3
assert(E3.use.n              .csname=="use:n")
assert(E3.use "n"            .csname=="use:n")
assert(E3 "use" .n           .csname=="use:n")
assert(E3 "use" "n"          .csname=="use:n")
assert(E3("use", "n")        .csname=="use:n")
assert(E3.tl_map_break""     .csname=="tl_map_break:")
assert(E3.tl_map_break()     .csname=="tl_map_break:")
assert(E3("tl_map_break", "").csname=="tl_map_break:")

--token.put_next{T "1"}
--print(L.detokenize_str(L.get_argument()))

prettyprint(L.expl_tokenize_unbalanced_braces [[123\ab\cd  \ef_g:h \\ \? \__ab

ab~cd {group{{ #$@!^_&*():<>\
x]])

prettyprint(L.doc_tokenize_unbalanced_braces [[123

4 5  6]])


--]==]

-- TODO token.scan_toks(false, true)  overrunning will not print Lua traceback.
end

