--unused ======== ======== ========
--do
local inspect = require "inspect"

	-- from /tmp/typst/src/syntax/ast.rs
	local shorthands = {
        {"*", "∗"},
        {"!=", "≠"},
        {":=", "≔"},
        {"::=", "⩴"},
        {"=:", "≕"},
        {"<<", "≪"},
        {"<<<", "⋘"},
        {">>", "≫"},
        {">>>", "⋙"},
        {"<=", "≤"},
        {">=", "≥"},
        {"->", "→"},
        {"-->", "⟶"},
        {"|->", "↦"},
        {">->", "↣"},
        {"->>", "↠"},
        {"<-", "←"},
        {"<--", "⟵"},
        {"<-<", "↢"},
        {"<<-", "↞"},
        {"<->", "↔"},
        {"<-->", "⟷"},
        {"~>", "⇝"},
        {"~~>", "⟿"},
        {"<~", "⇜"},
        {"<~~", "⬳"},
        {"=>", "⇒"},
        {"|=>", "⤇"},
        {"==>", "⟹"},
        {"<==", "⟸"},
        {"<=>", "⇔"},
        {"<==>", "⟺"},
        {"[|", "⟦"},
        {"|]", "⟧"},
        {"||", "‖"},
	}

	local cmdname_blacklist={relax=1, undefined_cs=1}
	local function is_valid(s)
		if token==nil then
			return true
		end
		return not cmdname_blacklist[token.create(s).cmdname]
	end

	local function create_tex_from_csname(s)
		-- if length 1
		if utf.len(s)==1 then
			return "\\"..s
		end
		-- if all alphabetical characters
		if s:match("^[a-zA-Z]+$") then
			return "\\"..s
		end
		return [[\csname ]]..s..[[\endcsname ]]
	end

	local function create_tex_from_typst_name(s)
		if is_valid("typ"..s) then
			return create_tex_from_csname("typ"..s)
		elseif is_valid(s) then
			return create_tex_from_csname(s)
		else
			error("invalid: "..s)
		end
	end


	local function parse(s, display)
		[[
		example:

		"sin theta + cos phi"
		output:
		"\sin \theta +\cos \phi "

		we need to parse the following:

		$ A = pi r^2 $
		$ "area" = pi dot.op "radius"^2 $
		$ cal(A) :=
			{ x in RR | x "is natural" } $
		$ x < y => x gt.eq.not y $
		$ sum_(k=0)^n k
			&= 1 + ... + n \
			&= (n(n+1)) / 2 $
		$ frac(a^2, 2) $
		$ vec(1, 2, delim: "[") $
		$ mat(1, 2; 3, 4) $
		$ lim_x =
			op("lim", limits: #true)_x $

		]]

		


		-- first replace the shorthands
		for _, v in ipairs(shorthands) do
			s = s:gsub(v[1], v[2])
		end

		-- split s into parts of
		-- * \<single character>
		-- * sequences of characters in [A-Za-z.], or characters with code > 127
		-- * quoted string "..."
		-- * anything else (symbols, space character, etc.)
		local parts={}
		-- TODO

		-- now process the parts
		-- need to handle:
		-- * ^(...) → ^{...}
		-- * _(...) → _{...}
		-- * (...)/(...) → \frac{...}{...}
		-- * other matching braces
		-- * Typst function calls
		-- * " | " → \mid
		-- 


		return inspect(parts)
	end

--	return {
--		parse=parse,
--		printdollar=function(s)
--			s = string.gsub(s, "\\par", " ")
--			-- if first and last character are spaces, use display math mode
--			if string.sub(s, 1, 1) == " " and string.sub(s, -1) == " " then
--				tex.print([[\begin{align*}]] .. parse(s) .. [[\end{align*}]])
--			else
--				tex.print("\\(" .. parse(s) .. "\\)")
--			end
--		end,
--	}
--end




print(parse([[sin theta + cos phi & => true \
123 + 456 & \(\( ... \) \{ \\ \
]]))
