do

	

local L=require "luamacrohelper"
local T=L.T
function ignore() end
ignore(T[""])
ignore(T.expandafter)
ignore(T.neverseenbefore)
ignore(T.neverseenbeforea)
ignore(T.neverseenbeforeb)

-- already include assertions

L.def("fff", function()
	assert(token.get_next().csname=="")
	assert(token.get_next().csname=="")  -- which will not actually get the token
	assert(L.get_next().csname=="anotherneverseen")
	assert(token.get_next().csname=="anotherneverseen")
	assert(token.get_next().csname=="def")
end)


L.set_macro(T.abc, {T.x, T.y})
assert(L.detokenize_str{T.abc, T.def} == [[\abc \def ]])
assert(L.detokenize_str{T.abc} == [[\abc ]])
assert(L.stringify_str (T.abc) == [[\abc]])
assert(L.tl_equal(L.get_macro(T.abc), {T.x, T.y}))

assert(L.meaning_str(L.bgroupT "A") == "begin-group character A")
assert(L.meaning_str(L.egroupT "B") == "end-group character B")
assert(L.stringify_str(L.egroupT "B") == "B")


local bgroup=L.bgroup
local egroup=L.egroup

--[[ test error message
L.runlocal{
	T.def, bgroup, egroup,
}

L.runlocal {T["use:n"]}
--]]

-- TODO token.scan_toks(false, true)  overrunning will not print Lua traceback.
end
