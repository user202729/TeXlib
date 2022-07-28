if not imperative_debug then
	imperative_debug=false
end


for k, v in pairs(require "imperative_tlutil") do
	_ENV[k]=v
end

setmetatable(_ENV, {__index=function(self, field)
	errorx("attempt to access undefined global variable "..tostring(field).."\n\n"..debug.traceback())
end})

local function getvars_paramtext(paramtext)  -- for example if paramtext='#x 123 #y' return '{[x.tok]=argtype.normal, [y.tok]=argtype.normal}'
	-- where x.tok is the .tok value of the token x
	local result={}
	for i=1, #paramtext-1 do  -- if the last one is mac_param then just assume it's trailing # for match-until-'{'
		local v=paramtext[i]
		if is_paramsign(v) then
			local nexttoken=paramtext[i+1]
			if is_paramsign(nexttoken) then
				errorx("two consecutive # in the parameter text")
			end
			result[nexttoken.tok]=argtype.normal
		end
	end
	return result
end

local function getvarsexpr(expr)  -- similar to above, but works on expression (allow two consecutive ##, and does not allow trailing #)
	local result={}
	local i, l=1, #expr
	while i<=l do
		if is_paramsign(expr[i]) then
			if i==l then
				error("unbalanced paramsign?")
			end
			if not is_paramsign(expr[i+1]) then
				result[expr[i+1].tok]=argtype.normal
			end
			i=i+2
		else
			i=i+1
		end
	end
	return result
end

local function namedef_to_macrodef(paramtext, replacementtext, statement)
	-- basically, this converts from "namedef" i.e. parameters are represented by arbitrary tokens/strings
	-- to "macrodef" i.e. they're indexed by numbers, the way TeX understands
	--
	-- e.g. paramtext = '#a #b #' replacementtext = '1 #a 2 #b ##'
	-- after the call paramtext = '#1 #2 #' replacementtext = '1 #1 2 #2 ##'
	--
	-- paramtext&replacementtext are tokenlists
	-- operate in-place.
	-- return a "param_tag" table which is ([1] → argtype.normal|argtype.Ntype, [2] → argtype.normal|argtype.Ntype, etc.)
	-- also return "name_seq" such as {[1] → ⟨token a⟩, [2] → ⟨token b⟩} for the example above
	--
	-- it's copied from statement.need, for e.g. new vars created by matchrm it defaults to argtype.normal
	--
	-- TODO maybe this duplicate a fair bit of the 2 functions above...?
	local used=0
	local tok_to_number_token={}  -- e.g. a.tok → 1, b.tok → 2, etc.
	local param_tag={}
	local name_seq={}
	for i=1, #paramtext-1 do
		local v=paramtext[i]
		if is_paramsign(v) then
			used=used+1
			if used>=10 then
				errorx("too many parameters")
			end
			local t=token.create(48+used, 12)
			if is_paramsign(paramtext[i+1]) then
				error("two consecutive # in the parameter text")
			end
			tok_to_number_token[paramtext[i+1].tok]=t
			param_tag[used]=statement.need[paramtext[i+1].tok] or argtype.normal
			name_seq[used]=paramtext[i+1]
			paramtext[i+1]=t
		end
	end
	local i, l=1, #replacementtext
	while i<=l do
		if is_paramsign(replacementtext[i]) then
			if i==l then
				error("unbalanced paramsign?")
			end
			if not is_paramsign(replacementtext[i+1]) then
				local z=tok_to_number_token[replacementtext[i+1].tok]
				if z==nil then

					---[[ some debug print
					for k, _ in pairs(tok_to_number_token) do
						prettyprint("k=", k)
					end
					--]]

					errorx("var #", replacementtext[i+1], " (tok=", replacementtext[i+1].tok, ") not found, paramtext=", paramtext, ", replacementtext=", replacementtext)
				end
				replacementtext[i+1]=z
			end
			i=i+2
		else
			i=i+1
		end
	end
	return param_tag, name_seq
end

local used_st={}  -- _linenumber → last used
local function next_st(linenumber)
	if used_st[linenumber]==nil then
		used_st[linenumber]=""
	else
		used_st[linenumber]=nextstr(used_st[linenumber])
	end
	return faketoken("stzz"..linenumber..used_st[linenumber])
end

local function interpolatelinenumber(body) -- operate in-place
	local lastlinenumber=0
	for i, v in ipairs(body) do
		if v._linenumber~=nil and v._linenumber>=0 then
			lastlinenumber=v._linenumber
			if i~=0 and body[i-1]._linenumber<0 then
				for j=1, i-1 do
					body[j]._linenumber=lastlinenumber
				end
			end
		else
			body[i]._linenumber=lastlinenumber
		end
	end
end

local function populatelinenumber(body) -- return new table with _linenumber property set
	local result={}
	local i=1
	local lastlinenumber=0
	while i<=#body do
		local t=body[i]
		if t.csname=="zzlinemark" then
			i=i+2
			local s=""
			while body[i].tok~=egroup.tok do
				s=s..string.char(body[i].mode)
				i=i+1
			end
			if #s==0 then
				error("line mark not followed by linenumber")
			end
			lastlinenumber=tonumber(s)
		else
			t=makefaketoken(t)
			if t._linenumber and t._linenumber>0 then  -- special case, nested compilation, so _linenumber already populated
				lastlinenumber=t._linenumber
			else
				t._linenumber=lastlinenumber
			end
			result[#result+1]=t
		end
		i=i+1
	end
	return result
end

local pending_definitions={}  -- list of {paramtext=paramtext, replacementtext=replacementtext, (something else)}
-- possible keys: see function finalize_generate_code() below

local function finalize_generate_code(statement, paramtext, replacementtext)  -- the macro itself is included in paramtext
	paramtext=slice(paramtext, 1)
	replacementtext=slice(replacementtext, 1)
	local param_tag=namedef_to_macrodef(paramtext, replacementtext, statement)
	for _, kv in pairs(pending_definitions) do
		if kv.caller.csname==paramtext[1].csname and kv.caller.active==paramtext[1].active then
			errorx("duplicate definition of ", paramtext[1])  -- not very efficient but okay
		end
	end

	statement.paramtext=paramtext
	statement.caller=paramtext[1]
	statement.paramtext2=slice(paramtext, 2)
	statement.replacementtext=replacementtext
	statement.z_optimizable=true  -- that is, the number of expansion steps for this is not important
	-- statement.r_optimizable:  that is, this statement will always be called in r-expansion mode
	statement.param_tag=param_tag


	table.insert(pending_definitions, statement)
	-- some properties are not needed (e.g. `need`, `produce`),
	-- but r_optimizable/allow_inline are copied over
end

local tokenfromtok_t={} -- actually this could be eliminated, but it's convenient
-- (also make it global. No harm?)

local function tokenfromtok(tok)
	local t=tokenfromtok_t[tok]
	if t==nil then
		if type(tok)=="number" then
			errorx(string.format("this cannot happen? tok %d (%x) does not correspond to a token", tok, tok))
		else
			errorx("this cannot happen? tok ", tok, " does not correspond to a token")
		end
	end
	return t
end

-- tokens: list of tokens, is_mark: function takes a token and return bool
local function compile_backquote(tokens, is_mark)
	local tokenstack=reverse(tokens)

	local prepare={}
	local processed={}
	while #tokenstack>0 do
		local t=popstack(tokenstack)
		if is_mark(t) then
			local kind=popstack(tokenstack)
			if kind.csname~=nil or (
				kind.mode~=string.byte "o" and
				kind.mode~=string.byte "O" and
				kind.mode~=string.byte "r"
			) then
				errorx("backquote: unknown token (", kind, ") follows mark!")
			end
			local tmpvar=randomvar()
			tokenfromtok_t[tmpvar.tok]=tmpvar

			if kind.mode==string.byte "O" then
				local innertokens=getbracegroup(tokenstack)
				local innerprepare, innerprocessed=compile_backquote(innertokens, is_mark)
				appendto(prepare, innerprepare)
				appendto(prepare, {faketoken "assignoperate", paramsign, tmpvar})
					appendto(prepare, innerprocessed)
					appendto(prepare, getbracegroup(tokenstack))
			else
				local innertokens=getbracegroup(tokenstack)
				local innerprepare, innerprocessed=compile_backquote(innertokens, is_mark)
				appendto(prepare, innerprepare)
				appendto(prepare, {faketoken("assign" .. string.char(kind.mode)), paramsign, tmpvar})
				appendto(prepare,    innerprocessed)
			end

			appendto(processed, {paramsign, tmpvar})

		else
			processed[#processed+1]=t
		end
	end
	return prepare, processed
end


local preprocessor_functions={
	Iexpandtobgroup=function(selftoken, output, inputstack)
		appendto(output, {expandafter, bgroup, iffalseT, egroup, fiT})
	end,
	Iexpandtoegroup=function(selftoken, output, inputstack)
		appendto(output, {iffalseT, bgroup, fiT, egroup})
	end,
	Iremovebgroup=function(selftoken, output, inputstack)
		local bgroup_=popstack(inputstack)
		if bgroup.tok~=bgroup_.tok then
			errorx("Iremovebgroup followed by ", bgroup_)
		end
		appendto(output, {iffalseT, bgroup_, fiT})
	end,
	Iremoveegroup=function(selftoken, output, inputstack)
		local egroup_=popstack(inputstack)
		if egroup.tok~=egroup_.tok then
			errorx("Iremoveegroup followed by ", egroup_)
		end
		appendto(output, {iffalseT, egroup_, fiT})
	end,
}

local generic_compile_code  -- function, will define later
-- signature: function generic_compile_code(functionname, body, passcontrol, statement_extra, outervar)

local function param_from_need(needsequence)  -- takes tokenfromtok implicitly
	local t={}
	for _, kv in ipairs(needsequence) do
		appendto(t, kv[2].paramtext(tokenfromtok(kv[1])))
	end
	return t
end

local function standard_paramtext(statement)
	local t={statement.caller}
	appendto(t, param_from_need(statement.needsequence))
	return t
end

--
--nextvalue: format
--tok → tokenlist
--the tokenlist has the form e.g. '{#a}'
--it must be in namedef format.
local function standard_nextvalue(next_statement)
	local nextvalue={}
	for k, v in pairs(next_statement.need) do
		nextvalue[k]=v.get_nextvalue(tokenfromtok(k))
	end
	return nextvalue
end

local function standard_replacementtext(next_statement, nextvalue)
	local replacementtext={next_statement.caller}
	for _, kv in ipairs(next_statement.needsequence) do
		if next_statement.need[kv[1]]==nil then
			errorx("internal error: variable ", tokenfromtok(kv[1]), " not found in .need!")
		end
		if nextvalue[kv[1]]==nil then
			errorx("internal error: variable ", tokenfromtok(kv[1]), " not found in nextvalue!")
		end
		appendto(replacementtext, nextvalue[kv[1]])
	end
	return replacementtext
end

local function generate_code_prepare(statement, statements)  -- return paramtext, replacementtext assume the operation is no-op
	local paramtext=standard_paramtext(statement)
	local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
	return paramtext, replacementtext
end

local function generate_code_noop(statement, statements)  -- well...
	finalize_generate_code(statement, generate_code_prepare(statement, statements))
end

local function check_var_not_outer(varname, context)
	if context.outerscope[varname.tok] then
		errorx("cannot assign to ", paramsign, varname, " already in outerscope")
	end
end

local command_handler={
	----------------------------------------------------------------------------
	-- the "primitives"

	matchrm=function(selftoken, lastlinenumber, stack, add_statement, context)
		local group=getbracegroupinside(stack)
		for _, v in ipairs(group) do if degree(v)~=0 then errorx "content of matchrm contain braces!" end end
		add_statement {
			debug=cati({faketoken "matchrm"}, wrapinbracegroup(group)),
			produce=getvars_paramtext(group),
			generate_code=function(statement, statements)
				local paramtext, replacementtext=generate_code_prepare(statement, statements)
				paramtext=cat(paramtext, group)
				finalize_generate_code(statement, paramtext, replacementtext)
			end,
		}
	end,

	putnext=function(selftoken, lastlinenumber, stack, add_statement, context)
		local group=getbracegroupinside(stack)
		add_statement {
			debug=cati({faketoken "putnext"}, wrapinbracegroup(group)),
			innerexpr=group,
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext, replacementtext=generate_code_prepare(statement, statements)
				replacementtext=cat(replacementtext, innerexpr_compiled)
				finalize_generate_code(statement, paramtext, replacementtext)
			end,
		}
	end,

	expandonce=function(selftoken, lastlinenumber, stack, add_statement, context)
		add_statement {
			debug={faketoken "expandonce"},
			generate_code=function(statement, statements)
				local paramtext, replacementtext=generate_code_prepare(statement, statements)

				local n=statement.nextindex
				replacementtext={expandafter, statements[n].caller}

				for _, kv in ipairs(statements[n].needsequence) do
					if kv[2].get_expandafter_sequence==nil then
						error("expandonce but some parameters (e.g. " .. tokenfromtok(kv[1]).csname .. ") are not expandafter-able")
					end
					appendto(replacementtext, kv[2].get_expandafter_sequence(tokenfromtok(kv[1])))
				end
				finalize_generate_code(statement, paramtext, replacementtext)
			end,
		}
	end,

	assertis=function(selftoken, lastlinenumber, stack, add_statement, context)
		local t=popstack(stack)
		assert(t.csname~=nil, "assertis must be followed with control sequence")
		local u=argtype[t.csname]
		assert(u~=nil, "argtype "..t.csname.." not found")

		local varname=getvarname(stack)
		add_statement {
			debug={faketoken "assertis", t, varname},
			need={[varname.tok]=argtype.normal},
			produce={[varname.tok]=u},
			generate_code=context.generate_code_noop,
		}
	end,

	conditionalgoto=function(selftoken, lastlinenumber, stack, add_statement, context)  -- star = peek
		local star=get_optional_star(stack)
		local conditional=getbracegroupinside(stack)
		local targetiftrue=popstack(stack)
		add_statement {
			debug=cati({faketoken "conditionalgoto"}, wrapinbracegroup(conditional), {targetiftrue}),
			conditionalgoto=targetiftrue,
			innerexpr=conditional,
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext=standard_paramtext(statement)
				local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
				local replacementtext2=standard_replacementtext(statements[statement.conditionalgoto], standard_nextvalue(statements[statement.conditionalgoto]))
				if star then  -- conditional might peek, don't eliminate common suffix
					finalize_generate_code(statement, paramtext, cat(
						innerexpr_compiled,
						optionalwrapinbracegroup(replacementtext2),
						optionalwrapinbracegroup(replacementtext)
					))
				else
					local l=commontokenlistbalancedsuffixlen(replacementtext, replacementtext2)
					finalize_generate_code(statement, paramtext, cat(
						innerexpr_compiled,
						optionalwrapinbracegroup(slice(replacementtext2, 1, #replacementtext2-l)),
						optionalwrapinbracegroup(slice(replacementtext, 1, #replacementtext-l)),
						slice(replacementtext, #replacementtext-l+1, #replacementtext)
					))
				end
			end,
		}
	end,

	label=function(selftoken, lastlinenumber, stack, add_statement, context)
		local labelname=popstack(stack)
		add_statement {
			debug={faketoken "label", labelname},
			label=labelname,
			generate_code=context.generate_code_noop,
		}
	end,

	["goto"]=function(selftoken, lastlinenumber, stack, add_statement, context)
		local labelname=popstack(stack)
		add_statement {
			debug={faketoken "goto", labelname},
			goto_=labelname,
			generate_code=context.generate_code_noop,
		}
	end,

	assign=function(selftoken, lastlinenumber, stack, add_statement, context)
		local varname=getvarname(stack)
		check_var_not_outer(varname, context)
		local content=getbracegroup(stack)
		add_statement {
			debug=cati({faketoken "assign", varname}, content),
			innerexpr=content,	
			produce={[varname.tok]=argtype.normal},
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext=standard_paramtext(statement)
				local nextvalue=standard_nextvalue(statement)
				nextvalue[varname.tok]=innerexpr_compiled
				local replacementtext=standard_replacementtext(statements[statement.nextindex], nextvalue)
				finalize_generate_code(statement, paramtext, replacementtext)
			end,
		}
	end,

	assigno=function(selftoken, lastlinenumber, stack, add_statement)  -- assigno #x {123}
		local varname=getvarname(stack)
		check_var_not_outer(varname, context)
		local content=getbracegroup(stack)
		add_statement {
			debug=cati({faketoken "assigno", varname}, content),
			innerexpr=content,
			assigno_tok=varname.tok,
			produce={[varname.tok]=argtype.normal},
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext=standard_paramtext(statement)
				local nextvalue=standard_nextvalue(statement)
				local next_statement=statements[statement.nextindex]
				assert(next_statement.needsequence[1][1]==varname.tok)
				nextvalue[varname.tok]=innerexpr_compiled
				local replacementtext=standard_replacementtext(next_statement, nextvalue)
				finalize_generate_code(statement, paramtext, cati(
					{expandafter, replacementtext[1], expandafter},
					slice(replacementtext, 2)
					))
			end,
		}
	end,

	assignoo=function(selftoken, lastlinenumber, stack, add_statement)
		local varname=getvarname(stack)
		check_var_not_outer(varname, context)
		local content=getbracegroup(stack)
		add_statement {
			debug=cati({faketoken "assignoo", varname}, content),
			innerexpr=content,
			assigno_tok=varname.tok,
			produce={[varname.tok]=argtype.normal},
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext=standard_paramtext(statement)
				local nextvalue=standard_nextvalue(statement)
				local next_statement=statements[statement.nextindex]
				assert(next_statement.needsequence[1][1]==varname.tok)
				nextvalue[varname.tok]=innerexpr_compiled
				local replacementtext=standard_replacementtext(next_statement, nextvalue)
				finalize_generate_code(statement, paramtext, cati(
					{expandafter, expandafter, expandafter, replacementtext[1], expandafter, expandafter, expandafter},
					slice(replacementtext, 2)
					))
			end,
		}
	end,

	expcall=function(selftoken, lastlinenumber, stack, add_statement, context)
		local content=getbracegroupinside(stack)
		add_statement {
			debug=cati({faketoken "expcall"}, content),
			innerexpr=content,
			generate_code=function(statement, statements, innerexpr_compiled)
				local paramtext=standard_paramtext(statement)
				local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
				finalize_generate_code(statement, paramtext, cat(innerexpr_compiled, replacementtext))
			end,
		}
	end,

	----------------------------------------------------------------------------
	-- macro-like (transform the code itself)

	-- TODO hack (does not check for expandability. will fix later)
	ucalllocal=function(selftoken, lastlinenumber, stack, add_statement, context)
		stack[#stack+1]=faketoken "expcall"
	end,

	["return"]=function(selftoken, lastlinenumber, stack, add_statement, context)
		local group=getbracegroup(stack)
		pushtostackfront(stack, 
			{faketoken "putnext"}, group,
			{faketoken "goto", context.labelfunctionend}
		)
	end,
	
	assignr=function(selftoken, lastlinenumber, stack, add_statement)  -- \assignr #x {\some function that is rdef-ed}
		local varname=getvarname(stack)
		local content=getbracegroupinside(stack)
		pushtostackfront(stack, 
			{faketoken "assigno", paramsign, varname, bgroup, faketoken "exp:w"}, content, {egroup}
		)
	end,

	assignc=function(selftoken, lastlinenumber, stack, add_statement)
		local varname=getvarname(stack)
		local content=getbracegroupinside(stack)
		pushtostackfront(stack, 
			{faketoken "assigno", paramsign, varname, bgroup, faketoken "csname"}, content, {faketoken "endcsname", egroup,
				faketoken "assertis", faketoken "Ntype", paramsign, varname
			}
		)
	end,

	backquote=function(selftoken, lastlinenumber, stack, add_statement)  -- lisp backquote-like
		-- syntax: \backquote {...}
		-- OR:     \backquote * {...}  (use * as the mark token instead of the default ,)
		local function is_mark(t)
			return t.csname==nil and t.mode==string.byte ","
		end

		if degree(stack[#stack])==0 then
			local mark_tok=popstack(stack).tok
			is_mark=function(t) return t.tok==mark_tok end
		end

		local tokens=getbracegroupinside(stack)
		local prepare, processed=compile_backquote(tokens, is_mark)
		pushtostackfront(stack, prepare, processed)
	end,

	assignoperate=function(selftoken, lastlinenumber, stack, add_statement)  -- \assignoperate #x {#x #y} {\matchrm...}
		local varname=getvarname(stack)
		local content=getbracegroupinside(stack)
		local operations=getbracegroupinside(stack)

		local localfn=next_st(lastlinenumber)
		generic_compile_code(localfn, operations, {faketoken "exp_end:"}, {r_optimizable=true, is_internal=true}, {})

		pushtostackfront(stack, 
			{faketoken "assigno", paramsign, varname, bgroup, faketoken "exp:w", localfn}, 
			content,
			{egroup}
		)
	end,

	conditional=function(selftoken, lastlinenumber, stack, add_statement, context)  -- star = peek
		local star=get_optional_star(stack)
		local condition=getbracegroup(stack)
		local codeiftrue=getbracegroupinside(stack)
		local codeiffalse=getbracegroupinside(stack)

		local labeltrue=randomlabel()
		local labelend=randomlabel()

		pushtostackfront(stack,   -- propagate the star. If star is nil it will be eliminated automatically
			{faketoken "conditionalgoto", star}, condition, {labeltrue},
			codeiffalse,
			{faketoken "goto", labelend,
			faketoken "label", labeltrue},
			codeiftrue,
			{faketoken "label", labelend}
		)
	end,

	-- usage: e.g. \texconditional <optional star> { \ifnum 1 = 2~ } {true} {false}
	texconditional=function(selftoken, lastlinenumber, stack, add_statement, context)  -- star = peek
		local star=get_optional_star(stack)
		local condition=getbracegroupinside(stack)

		pushtostackfront(stack,
			{faketoken "conditional", star}, {bgroup}, condition, {faketoken "use_ii_to_i:w", faketoken "fi", faketoken "use_ii:nn", egroup}
		)
	end,

	["while"]=function(selftoken, lastlinenumber, stack, add_statement, context)
		local codebefore=getbracegroupinside(stack)
		local condition=getbracegroup(stack)
		local code=getbracegroupinside(stack)

		local labelcheck=randomlabel()
		local labelcontinue=randomlabel()
		pushtostackfront(stack, 
			{faketoken "goto", labelcheck,
			faketoken "label", labelcontinue},
			code,
			{faketoken "label", labelcheck},
			codebefore,
			{faketoken "conditionalgoto"}, condition, {labelcontinue}
		)
	end,

	putnextwithexpand=function(selftoken, lastlinenumber, stack, add_statement, context)
		local tokens=getbracegroupinside(stack)
		local commands=getbracegroupinside(stack)
		for i, v in pairs(tokens) do tokens[i]=makerealtoken(v) end
		for i, v in pairs(commands) do commands[i]=makerealtoken(v) end
		pushtostackfront(stack, {faketoken "putnext"}, wrapinbracegroup(withexpand_compile(tokens, commands)))
	end,

	rcall=function(selftoken, lastlinenumber, stack, add_statement, context)
		local tokens=getbracegroupinside(stack)
		pushtostackfront(stack, {faketoken "putnext",
			bgroup, faketoken "exp:w"}, tokens, {egroup,
			faketoken "expandonce"})
	end,

	ocall=function(selftoken, lastlinenumber, stack, add_statement, context)
		local tokens=getbracegroup(stack)
		pushtostackfront(stack, {faketoken "putnext"}, tokens, {faketoken "expandonce"})
	end,

	pretty=function(selftoken, lastlinenumber, stack, add_statement, context)
		local content=getbracegroupinside(stack)
		pushtostackfront(stack, {faketoken "expcall",
			bgroup, faketoken "prettye:n", bgroup, faketoken("[L"..lastlinenumber.."]:")}, content, {egroup, egroup})
	end,

	prettyw=function(selftoken, lastlinenumber, stack, add_statement, context)
		pushtostackfront(stack, {faketoken "expcall", bgroup,
			faketoken "prettye:nw", faketoken("[L"..lastlinenumber.."]:"),
		egroup})
	end,
}

-- functionname: single token, body: tokenlist (possibly with _linenumber info added)
-- passcontrol: tokenlist consist of tokens that will be prepended when this function returns
-- return the .needsequence of the function itself
function generic_compile_code(functionname, body, passcontrol, statement_extra, outervar)
	assert(type(outervar)=="table")

	if statement_extra.is_internal then
		prettyprint("see", functionname, "as internal")
	end

	for _, t in ipairs(body) do tokenfromtok_t[t.tok]=t end


	--zblock etc. should not propagate the original variable value to inside
	local tmp=outervar
	outervar=nil
	outerscope={
		layer=1,
		prefix={paramsign, paramsign},
	}
	for k, v in pairs(tmp) do
		if k~="prefix" and k~="layer" then  -- yes it's going to bite...
			outerscope[k]={paramsign, tokenfromtok(k)}
		end
	end


	local labelfunctionend=randomlabel()
	body=cati(body, {faketoken "label", labelfunctionend})

	------ very special preprocessor (TODO keep linenumbers)
	local stack=reverse(body)
	body={}
	while #stack>0 do
		local t=popstack(stack)
		local handler=preprocessor_functions[t.csname]
		if handler then
			--if imperative_debug then
			--	load("preprocessor_functions." .. t.csname .. "(...)")(t, body, stack)
			--else
				handler(t, body, stack)
			--end
		else
			body[#body+1]=t
		end
	end

	------ resume to normal processing
	stack=reverse(body)

	local statements={
		{
			debug={faketoken "start"},
			caller=functionname,
			generate_code=generate_code_noop,
			nextindex=2,
			linenumber=-1,
		}  -- this is problematic, need to manually copy statement_extra as well...
	}

	local lastlinenumber=0

	local function add_statement(statement)
		
		if #statements==0 then
			statement.caller=functionname
		else
			statement.caller=next_st(lastlinenumber)
			statement.is_internal=true  -- i.e. it's possible to eliminate/rename this function, "not public API"
		end

		for k, v in pairs(statement_extra) do
			statement[k]=v
		end
		statement.linenumber=lastlinenumber
		statements[#statements+1]=statement
	end


	local context={
		labelfunctionend=labelfunctionend,
		generate_code_noop=generate_code_noop,
		outerscope=outerscope,
	}

	while #stack>0 do
		local t=popstack(stack)
		if t._linenumber~=nil then
			lastlinenumber=t._linenumber
		end
		if t.csname==nil or command_handler[t.csname]==nil then
			errorx("invalid token seen: (", t, ") on line ", lastlinenumber)
		end
		print("======== processing line", lastlinenumber)
		command_handler[t.csname](t, lastlinenumber, stack, add_statement, context)
	end


	local labelpos={}  -- [label.tok] -> index
	for i, v in ipairs(statements) do
		if v.label then
			labelpos[v.label.tok]=i
		end
	end

	for i, v in ipairs(statements) do
		v.comefrom={}
		if v.produce==nil then v.produce={} end
	end

	for i=1, #statements-1 do
		local v=statements[i]

		if v.goto_ then
			v.nextindex=labelpos[v.goto_.tok]
		else
			v.nextindex=i+1
		end
		table.insert(statements[v.nextindex].comefrom, i)

		if v.conditionalgoto then
			v.conditionalgoto=labelpos[v.conditionalgoto.tok]
			table.insert(statements[v.conditionalgoto].comefrom, i)
		end
	end


	--[[
	now each statement in `statements` has:

	.nextindex = some index
	.conditionalgoto = some index (in labelpos), if it's a conditionalgoto

	.need: set of var tok needed by that statement  (might be omitted. If omitted deduced from compiling innerexpr, or if innerexpr not available, is empty)
	.produce: ↑ set of var tok produced by that statement

	.caller: some random token generated for this line of code...

	other primitive-specific things
	]]

	-- propagate the `produce` values

	--for tok, _ in pairs(outerscope) do
	--if tok~="layer" and tok~="prefix" then
	--	statements[1].produce[tok]=argtype.normal
	--	end
	--end

	local propagate

	local function propagate2(j, tok)
		-- here some statement before v produces tok as single token.
		-- check if v also produces tok as single token.
		local v=statements[j]

		if v.produce[tok]~=nil then
			return
		end

		assert(#v.comefrom>0)

		local result_type=nil
		for _, k in pairs(v.comefrom) do
			local other_produced_type=statements[k].produce[tok]
			if other_produced_type==nil then
				-- not propagated yet? For now cannot determine what result_type this statement will produce
				-- will determine later.
				return
			end

			if result_type==nil then
				result_type=other_produced_type
			else
				result_type=argtype_either[result_type][other_produced_type]
			end
			assert(result_type~=nil)
		end

		if v.produce[tok]~=result_type then
			v.produce[tok]=result_type
			propagate(j, tok)
		end
	end

	propagate=function(i, tok)
		-- here i produces tok as single token. Propagate it to j where i goes to j.
		local v=statements[i]
		if v.nextindex~=nil then
			propagate2(v.nextindex, tok)
		end
		if v.conditionalgoto~=nil then
			propagate2(v.conditionalgoto, tok)
		end
	end

	for i=1, #statements-1 do
		for k, v in pairs(statements[i].produce) do
			propagate(i, k)
		end
	end

	-- before processing need value, need to compile all the innerexpr
	for i, v in ipairs(statements) do
		if v.innerexpr then
			assert(v.need==nil, "internal error both need and innerexpr non-nil")

			local current_scope={}
			--setmetatable(current_scope, {__index=outerscope})
			for k, v in pairs(outerscope) do  
				current_scope[k]=v
			end

			-- except for matchrm, propagate and need are roughly the same
			for k, v in pairs(v.produce) do
				current_scope[k]={paramsign, tokenfromtok(k)}
			end
			
			v.innerexpr_compiled, v.need=compile_outer(v.innerexpr, current_scope)
			v.need=getvarsexpr(v.innerexpr_compiled)  -- TODO???
		elseif v.need==nil then
			v.need={}
		end
	end
		

	-- propagate the `need` values
	local function propagate(i, tok)
		local v=statements[i]
		assert(v.need[tok])
		for _, j in pairs(v.comefrom) do
			if not statements[j].need[tok] and not statements[j].produce[tok] then
				statements[j].need[tok]=argtype.normal
				propagate(j, tok)
			end
		end
	end
	for i=1, #statements-1 do
		for k, _ in pairs(statements[i].need) do
			propagate(i, k)
		end
	end

	-- then, convert `need` table to indexed table (fixed order)
	for _, v in ipairs(statements) do
		local n={}
		for var_tok, var_kind in pairs(v.need) do
			-- var_tok: .tok value
			-- var_kind: for example argtype.Ntype or argtype.normal
			n[#n+1]={var_tok, var_kind}
		end
		v.needsequence=n
	end

	-- special handling for assigno: needsequence of next need a particular order
	for _, v in ipairs(statements) do
		local assigno_tok=v.assigno_tok
		if assigno_tok~=nil then
			local n=statements[v.nextindex].needsequence
			local old=#n
			local okay=false
			for i=1, #n do
				if n[i][1]==assigno_tok then
					n[1], n[i]=n[i], n[1]
					okay=true
					break
				end
				-- it's also possible if the variable ends up being unused
			end

			if not okay then
				local len=#n
				n[1], n[len+1]={assigno_tok, argtype.normal}, n[1]
			end

			assert(#n>=old)
		end
	end

	local function debug_print_statements()
		prettyprint "========"
		for i, v in ipairs(statements) do

			local s="need="
			if v.need then
				for _, kv in ipairs(v.needsequence) do
					local k, v=kv[1], kv[2]
				--for k, v in pairs(v.need) do
					s=s..tostring(k)
					if v.is_a[argtype.Ntype] then s=s.."^" end  -- just for debug purpose
					s=s..","
				end
			end
			s=s.."/"

			prettyprint(
				{v.caller, i..". → "..tostring(v.nextindex).."|"..tostring(v.conditionalgoto)},
				v.debug,
				{s}
			)
		end
		prettyprint "========"
	end

	--debug_print_statements()

	-- now, generate code...
	for i=1, #statements-1 do
		if statements[i].generate_code then --TODO everything must have handler
			local success, val=xpcall(function()
				statements[i]:generate_code(statements, statements[i].innerexpr_compiled)
			end, debug.traceback)
			if not success then
				debug_print_statements()
				errorx(
					"while processing statement "..i..", line "..statements[i].linenumber..":\n\n\n"
					.. "======== old traceback start ========\n"
					.. tostring(val)
					.. "\n======== old traceback end ========\n\n\n")
			end
		end
	end
	assert(#statements>0)
	assert(#statements[#statements].needsequence==0)
	finalize_generate_code(statements[#statements], {statements[#statements].caller}, passcontrol)

	return statements[1].needsequence
end

local outervarmarker={}  -- marker

--[[
`scope` is a table like this...

{ layer=0, prefix=# }  -- topmost layer (layer 0 is special, don't need # doubling)
{ layer=1, a.tok=#1, b.tok=#2, prefix=## }  -- inside \scope #a #b 
{ layer=2, a.tok=#1, b.tok=#2, c.tok=##1, prefix=#### }  -- inside \scope #a #b → \scope #c

this does assume that no tok value is equal to "layer" or "prefix" however.

also the special outervarmarker value is used like this

{ a.tok=outervarmarker }

means a.tok is a imperative-variable defined outside e.g. \rfunction \f #a { \putnext { \rblock { ... #a  ... } } },
then while compiling the inner rblock, 'a' is outervar (e.g. cannot be reassigned).

]]


local compile_outer_handler={
	--rblock=function(stack, body, scope, lastlinenumber)
	--	local param=getuntilbrace(stack)
	--	local inner=getbracegroupinside(stack)
	--	--appendto(body, 
	--end,
	zblock=function(stack, body, scope, lastlinenumber)
		local localfn=next_st(lastlinenumber)
		local content=getbracegroupinside(stack)
		local needsequence=generic_compile_code(localfn, content, {}, {}, scope)
		-- TODO somehow mark this function as internal

		body[#body+1]=localfn
		for _, v in pairs(needsequence) do
			local tok=v[1]
			if not scope[tok] then
				errorx("internal error var ", tokenfromtok(tok), " not found")
			end
			appendto(body, wrapinbracegroup(scope[tok]))  -- TODO optimization: brace can be omitted sometimes
		end
	end,
	--rfunction=function(stack, body, scope, lastlinenumber)
	--end,
	--zfunction=function(stack, body, scope, lastlinenumber)
	--end,

	scopeunbraced=function(stack, body, scope, lastlinenumber)
		local paramtext=getuntilbrace(stack)
		if #paramtext%2~=0 then errorx("scope paramtext wrong format") end

		local content=getbracegroupinside(stack)

		for i=1, #paramtext, 2 do
			if not is_paramsign(paramtext[i]) then
				errorx("scope paramtext=", paramtext, ",token "..i.." is ", paramtext[i], " not a paramsign")
			end
		end

		local newscope={}
		for k, v in pairs(scope) do newscope[k]=v end
		assert(scope.layer>=0)
		newscope.layer=scope.layer+1
		newscope.prefix=cat(scope.prefix, scope.prefix)

		if #paramtext>9*2 then
			error("too many args, impossible")
		end
		for i=2, #paramtext, 2 do
			local tok=paramtext[i].tok
			if newscope[tok] then
				errorx("variable shadowing in nested scope ", paramtext[i])
			end
			newscope[tok]=cat(scope.prefix, {token.create(48+i/2, 12)})
		end

		local innercontent=(compile_outer(content, newscope)) -- brace, only first arg
		appendto(body, innercontent)
	end,
	---------------- macro-like

	scope=function(stack, body, scope, lastlinenumber)
		local paramtext=getuntilbrace(stack)
		local content=getbracegroup(stack)
		pushtostackfront(stack, cati({faketoken "scopeunbraced"}, paramtext, {bgroup}, content, {egroup}))
	end,


	scopevar=function(stack, body, scope, lastlinenumber)  -- \scopevar #a, #b {  →  #1, #2 \scope #a #b {
		local paramtext=getuntilbrace(stack)

		-- abuse the function a bit
		-- assume currently paramtext = '#a, #b'
		local param_tag, name_seq=namedef_to_macrodef(paramtext, {}, {need={}})

		--now paramtext = '#1, #2'
		--need to double the # as necessary
		local old=paramtext
		paramtext={}
		for _, t in ipairs(old) do
			if is_paramsign(t) then
				appendto(paramtext, scope.prefix)
			else
				paramtext[#paramtext+1]=t
			end
		end

		-- construct a sequence '#a #b' to be passed to \scope
		local name_seq_as_args={}
		for _, v in ipairs(name_seq) do
			appendto(name_seq_as_args, {paramsign, v})
		end


		pushtostackfront(stack,
				cat(paramtext,  -- such as '##1, ##2'
				{faketoken "scope"}, name_seq_as_args  -- such as \scope #a #b
				))
	end,
}


--body: tokenlist
--scope: format explained above

--return
-- * the compiled tokenlist itself (after replacing according to scope), and 
-- * the need table i.e. {t.tok=argtype, ...}   which is subset of scope

--recall that layer 0 is treated specially
function compile_outer(body, scope)
	if scope==nil then
		scope={
			layer=0,
			prefix={paramsign},
		}
	end

	for _, t in ipairs(body) do tokenfromtok_t[t.tok]=t end
	body=populatelinenumber(body)
	local stack=reverse(body)
	body={}

	local lastlinenumber=-1
	while #stack>0 do
		local t=popstack(stack)
		if t._linenumber then
			lastlinenumber=t._linenumber
		end
		print("======== processing line", lastlinenumber)

		if scope.layer>0 and is_paramsign(t) then
			local n=popstack(stack)
			if is_paramsign(n) then
				for i=1, 1<<(scope.layer-1) do
					appendto(body, {t, n})  -- '##', keep verbatim (multiply by scope depth)
				end
			else
				local s=scope[n.tok]
				if not s then
					errorx("variable ", n, " is not in scope")
				end
				appendto(body, s)
			end
		else
			local handler=compile_outer_handler[t.csname]
			if handler~=nil then
				if imperative_debug then
					--so that debug.traceback prints out the functionname
					load("({...})[1]." .. t.csname .. "(select(2, ...))")(compile_outer_handler, stack, body, scope, lastlinenumber)
				else
					handler(stack, body, scope, lastlinenumber)
				end
			else
				body[#body+1]=t
			end
		end
	end

	--changed approach a bit. Instead of getting need while compiling body, getting need after compiling body
	local need={}
	if scope.layer>0 then
		need=getvarsexpr(body)
	end

	return body, need
end

-- statement_extra: extra properties to be appended to the statement object
function generic_def_call(passcontrol, statement_extra)
	local header=token.scan_toks()
	if #header==0 then error("header cannot be empty") end
	local functionname=header[1]
	local body=token.scan_toks()

	args=slice(header, 2)
	if #args>0 then
		body=cati(
		{faketoken "matchrm"},
		wrapinbracegroup(args),
		body)
	end

	-- special handler: get linenumber for each token in body
	body=populatelinenumber(body)

	generic_compile_code(functionname, body, passcontrol, statement_extra, {})
end

imperative_nextstatement_properties={}

function rdef_call()
	local tmp=imperative_nextstatement_properties
	tmp.r_optimizable=true
	imperative_nextstatement_properties={}
	generic_def_call({faketoken "exp_end:"}, tmp)
end

function zdef_call()
	local tmp=imperative_nextstatement_properties
	imperative_nextstatement_properties={}
	generic_def_call({}, tmp)
end

local lib_definitions={}

function register_lib_fn()
	local prefix=token.scan_toks()
	local caller=token.scan_toks()
	assert(#caller==1)
	caller=caller[1]
	local paramtext2=token.scan_toks()
	local replacementtext=token.scan_toks()
	table.insert(lib_definitions, {
		prefix=prefix,
		caller=caller,
		paramtext=cat({caller}, paramtext2),  -- "backward compatibility"
		paramtext2=paramtext2,
		replacementtext=replacementtext,
		allow_inline=true,
	})
end

function debug_rdef()
	for _, pr in ipairs(pending_definitions) do
		local extra_status=""
		if pr.is_internal then extra_status=extra_status.."[internal]" end
		prettyprint(extra_status, pr.paramtext, "→", pr.replacementtext)
	end
end

local function get_execute_pending_definitions_tl(pending_definitions)
	local result={}
	for _, pr in ipairs(pending_definitions) do
		result=cati(result, {faketoken "long", faketoken "def"}, pr.paramtext, wrapinbracegroup(pr.replacementtext))
	end
	return result
end

function print_tlrepr()
	print("\n\n")
	print(get_tlreprx(get_execute_pending_definitions_tl(pending_definitions)))
	print("\n\n")
end

function execute_pending_definitions()
	print_fake_tokenlist(get_execute_pending_definitions_tl(pending_definitions))
	pending_definitions={}
end

local hide_error_optimization=true  -- whether to apply optimizations that might turn code that errors to code that does unexpected things

function optimize_pending_definitions()
	local function refcount(tok)
		-- inefficient...
		local result=0
		for _, v in pairs(pending_definitions) do
			local replacementtext=v.replacementtext
			for _, t in ipairs(replacementtext) do
				if t.tok==tok then
					result=result+1
					break
				end
			end
		end
		return result
	end

	local function find_def_generic(t, caller)  -- given a token, return (index, t[index])
		-- where t is pending_definitions or lib_definitions
		for j, w in pairs(t) do
			if w.caller.csname==caller.csname then
				return j, w
			end
		end
		return nil, nil
	end

	local function find_def_include_library(caller)  -- return the statement only, not the index (or null if not found)
		local _, result=find_def_generic(lib_definitions, caller)
		if not result then _, result=find_def_generic(pending_definitions, caller) end
		return result
	end

	local function replace_macro(search, replace)
		for _, w in pairs(pending_definitions) do
			for j=2, #w.paramtext do assert(w.paramtext[j].tok~=search.tok) end
			for j, t in ipairs(w.replacementtext) do if t.tok==search.tok then
				w.replacementtext[j]=replace
			end end
		end
	end



	while true do
		local done_anything=false

		-- optimize by replacing macro X with macro Y if X is defined to be Y without any arguments
		for _, v in ipairs(pending_definitions) do if v.z_optimizable and v.is_internal then
			local paramtext, replacementtext, caller=v.paramtext, v.replacementtext, v.caller
			if #paramtext==1 and #replacementtext==1 then
				local replacement=replacementtext[1]
				replace_macro(caller, replacement)
				done_anything=true
			end
		end end


		for _, v in ipairs(pending_definitions) do if v.z_optimizable then
			local paramtext, replacementtext=v.paramtext, v.replacementtext

			-- optimize special pattern \expandafter \<macro expands to nothing>
			if #replacementtext>=2
				and replacementtext[1].csname=="expandafter"
			then
				local w=find_def_include_library(replacementtext[2])
				if w~=nil and #w.paramtext==1 and #w.replacementtext==0 then
					v.replacementtext=slice(replacementtext, 3)
					done_anything=true
				end
			end

			-- optimize special pattern \expandafter A \expandafter B \exp:w \mymacro ...
			-- where \mymacro expansion starts with \exp_end:
			-- so \exp:w \mymacro is actually equivalent to \mymacro'o  (one expansion step expands to something)
			if #replacementtext>=6
				and replacementtext[1].csname=="expandafter"
				and replacementtext[3].csname=="expandafter"
				and replacementtext[5].csname=="exp:w"
			then
				local w=find_def_include_library(replacementtext[6])
				if w and w.replacementtext[1] and w.replacementtext[1].csname=="exp_end:"
					and refcount(w.caller.tok)==1 -- TODO
				then
					w.replacementtext=slice(w.replacementtext, 2)
					v.replacementtext=cati(slice(replacementtext, 1, 4), slice(replacementtext, 6))
					done_anything=true
				end
			end

		end end

		
		-- optimize special pattern \expandafter \exp_end: \exp:w
		for _, v in ipairs(pending_definitions) do if v.r_optimizable then
			local paramtext, replacementtext=v.paramtext, v.replacementtext
			if #replacementtext>=3
				and replacementtext[1].csname=="expandafter"
				and replacementtext[2].csname=="exp_end:"
				and replacementtext[3].csname=="exp:w"
			then
				v.replacementtext=slice(replacementtext, 4)
				done_anything=true
			end
		end end

		-- optimize by deduplicating macros with same definition
		for i, v in ipairs(pending_definitions) do if v.is_internal then
			for j=i+1, #pending_definitions do
				local w=pending_definitions[j]
				if tl_equal(v.paramtext2, w.paramtext2) and tl_equal(v.replacementtext, w.replacementtext) then
					replace_macro(v.caller, w.caller)
					done_anything=true
					break --inner loop
				end
			end
		end end

		-- deduplicating macros with same definition as a library function
		for i, v in ipairs(pending_definitions) do if v.is_internal then
			for j, w in ipairs(lib_definitions) do
				if tl_equal(v.paramtext2, w.paramtext2) and tl_equal(v.replacementtext, w.replacementtext) then
					replace_macro(v.caller, w.caller)
					done_anything=true
					break --inner loop
				end
			end
		end end

		-- optimize by simulating some expansion steps within macro definition
		for _, v in ipairs(pending_definitions) do if v.z_optimizable then
		--for i=1, #pending_definitions do local v=pending_definitions[i] if v and v.z_optimizable then
			local paramtext, replacementtext=v.paramtext, v.replacementtext
			local caller=paramtext[1]

			-- compute target_replacementtext_pos (first "nontrivial" token that is going to be expanded)
			local target_replacementtext_pos=1
			while replacementtext[target_replacementtext_pos] and replacementtext[target_replacementtext_pos].csname=="expandafter" do
				if replacementtext[target_replacementtext_pos+1] and is_paramsign(replacementtext[target_replacementtext_pos+1]) then
					if replacementtext[target_replacementtext_pos+1] and is_paramsign(replacementtext[target_replacementtext_pos+1]) then
						-- skip through a ##
						target_replacementtext_pos=target_replacementtext_pos+3
					else
						-- #1, #2 etc.
						local paramnumber=get_paramnumber(replacementtext[target_replacementtext_pos+2])
						assert(paramnumber)
						if v.param_tag[paramnumber].is_a[argtype.single_token] then
							-- skip through this token as usual
							target_replacementtext_pos=target_replacementtext_pos+3
						else
							-- attempt to expand the second token inside #1. Cannot do anything
							break
						end
					end
				else
					-- normal token, skip through it
					target_replacementtext_pos=target_replacementtext_pos+2
				end
			end

			local target=replacementtext[target_replacementtext_pos]
			local is_r_expansion=false
			while target and ({romannumeral=true, ["exp:w"]=true})[target.csname] do
				is_r_expansion=true
				target_replacementtext_pos=target_replacementtext_pos+1
				target=replacementtext[target_replacementtext_pos]
			end

			if target_replacementtext_pos~=1 and target and target.csname==nil and not is_paramsign(target) then
				-- user have macro \expandafter ... <firsttoken> where firsttoken is unexpandable
				-- actually followed by ## is also a weird case, but ignore it for now.
				errorx("weird? expandafter chain do nothing (in function ", v.caller, ")")
			end

			-- remove '\exp:w \expandafter \exp_end:' at appropriate places
			if target then
				assert(target.csname~="exp:w")
				if target.csname=="expandafter" and  --TODO write tests for this. This depends on some assumptions in other parts of the code
					replacementtext[target_replacementtext_pos+1] and
					replacementtext[target_replacementtext_pos+1].csname=="exp_end:"
				then
					done_anything=true
					v.replacementtext=cati(slice(replacementtext, 1, target_replacementtext_pos-2), slice(replacementtext, target_replacementtext_pos+2))
					target=nil  -- break the next check
				end
			end

			local caller_param_tag=v.param_tag
			if target and target.csname and target.csname~=caller.csname  -- this might be violated if user intentionally make infinite loop or something-else, anyway better not touching it
				--and refcount(target.tok)==1   -- TODO may bloat the code but...
			then
				assert(not target.active)
				local target_def=find_def_include_library(target)
				if target_def
					and (target_def.is_internal or target_def.allow_inline)
				then
					local target_paramtext, target_replacementtext=target_def.paramtext, target_def.replacementtext
					if true
						--and not have_double_arg_use(target_replacementtext)  -- TODO disabling this might exponentially increase the code size
					then
						local matched_args, stack=try_grab_args(caller_param_tag, target_paramtext, slice(replacementtext, target_replacementtext_pos+1))

						if matched_args then
							-- can be optimized
							-- we have: v.replacementtext=replacementtext= <some tokens before target_replacementtext_pos>   \target {args...} rest...
							-- currently:
							--
							--   \target{args...} should expand to
							--     target_replacementtext
							--     [where each #i is replaced with matched_args[i]]
							--
							--           rest=reverse(stack)
							done_anything=true

							if is_r_expansion then  -- need to keep the exp:w etc.
								v.replacementtext=cati(
									slice(v.replacementtext, 1, target_replacementtext_pos-1),
									substitute_replacementtext(target_replacementtext, matched_args),
									reverse(stack))
							else  -- remove the expandafter chain
								local new_replacementtext={}
								for i=2, target_replacementtext_pos-1, 2 do
									new_replacementtext[#new_replacementtext+1]=replacementtext[i]
								end
								appendto(new_replacementtext, substitute_replacementtext(target_replacementtext, matched_args))
								appendto(new_replacementtext, reverse(stack))
								v.replacementtext=new_replacementtext
							end
							-- target will be deleted later if necessary (if its refcount=0)


						elseif not is_r_expansion and target_replacementtext_pos==5 and find_def_include_library(replacementtext[2]) and degree(replacementtext[4])==1 and hide_error_optimization then
							-- format: expandafter \X expandafter { \target ... }, where target is a user-defined macro (so one-step expansion of it cannot change the balance)
							-- then attempt to expand \X one-step over it
							-- actually this can be made more general (it's okay for the \expandafter to not stop at the first, as long as it's inside the first group)


							--TODO
							--local matching_close_brace=5

							--errorx("okay", v.caller)
						end
					end
				end
			end
		end end

		-- remove internal ones with refcount==0
		local pending_definitionsx={}
		for _, v in ipairs(pending_definitions) do
			local caller=v.caller
			if v.is_internal and refcount(caller.tok)==0 then
				done_anything=true
			else
				pending_definitionsx[#pending_definitionsx+1]=v
			end
		end
		pending_definitions=pending_definitionsx

		if not done_anything then break end
	end
			
end

do  -- block for withexpand.
	local tokens
	local commands
	local is_label
	local last_index1
	local pending_reindex
	local reindex -- [old index] = (new index | after_end)

	local after_end={}  -- unique marker

	local function reset_local_vars(tokens_)
		tokens=tokens_
		commands={}
		is_label={}  -- this is indexed from 1 to #tokens. Nil means not sure, true → must be label, false → must not be label
		last_index1=-1
		pending_reindex={}
		reindex={}
	end

	local function sub_index(sub)
		local offset=find_subsequence_checked(sub, tokens)
		for j=1, #sub do
			if is_label[offset+j]==true then
				errorx("index "..(offset+j).." was previously marked as label in ", tokens, "token at index=", tokens[offset+j])
			end
			is_label[offset+j]=false
		end
		return offset+1
	end

	local function label_index(label)
		local offset=find_subsequence_checked(label, tokens)
		for j=1, #label do
			if is_label[offset+j]==false then
				prettyprint("index "..(offset+j).." was previously marked as non-label in ", tokens, "token at index=", tokens[offset+j])
				error()
			end
			is_label[offset+j]=true
		end
		return offset+1
	end

	local function cmd_index(cmd, cmdarg)
		-- cmd is either {\expandat} or {\expandatlabel}
		if #cmd~=1 or (cmd[1].csname~="expandat" and cmd[1].csname~="expandatlabel") then
			errorx("Unexpected cmd=", cmd)
		end
		if cmd[1].csname=="expandat" then
			return sub_index(cmdarg)
		else
			return label_index(cmdarg)
		end
	end

	local function add_command(index1, index2)
		if index1>index2 then
			errorx("expansion argument must be after expansion source")
		end
		if index1<last_index1 then
			errorx("commands must be listed in increasing left endpoint order")
		end
		last_index1=index1
		commands[#commands+1]={index1, index2}
	end

	local function add_single_token_marker(first, len)
		if #commands==0 then
			commands[1]={}
		end
		if len<=0 then errorx("empty part cannot be single token") end
		local last=commands[#commands]
		if not last.single_token_marker then last.single_token_marker={} end
		last.single_token_marker[#last.single_token_marker+1]={first, len}
	end

	withexpand_cmds={  -- global for access from TeX code.
		expandat=function()
			local sub=token.scan_toks()  -- none of `sub` can be a label.
			add_command(1, sub_index(sub))
		end,
		expandatlabel=function()
			local label=token.scan_toks()
			add_command(1, label_index(label))
		end,
		onlabel=function()
			local label=token.scan_toks()
			local cmd=token.scan_toks()  -- expandat or expandatlabel
			local cmdarg=token.scan_toks()
			add_command(label_index(label), cmd_index(cmd, cmdarg))
		end,
		marklabel=function()  -- this function is not useful by itself, mostly for debugging purpose
			local label=token.scan_toks()
			label_index(label)
		end,
		after=function()
			local sub=token.scan_toks()
			local cmd=token.scan_toks()  -- expandat or expandatlabel
			local cmdarg=token.scan_toks()
			add_command(sub_index(sub)+#sub, cmd_index(cmd, cmdarg))
		end,
		before=function()
			local sub=token.scan_toks()
			local cmd=token.scan_toks()  -- expandat or expandatlabel
			local cmdarg=token.scan_toks()
			add_command(sub_index(sub), cmd_index(cmd, cmdarg))
		end,
		assertissingletoken=function()
			local sub=token.scan_toks()
			add_single_token_marker(sub_index(sub), #sub)
		end,
		assertissingletokenbetweenlabel=function()
			local a=token.scan_toks()
			local b=token.scan_toks()
			local indexa=label_index(a)
			local indexb=label_index(b)
			local innerlen=indexb-indexa-#a
			add_single_token_marker(indexa+#a, innerlen)
		end,
	}

	local function find_index(blocks, index)
		local r=reindex[index]
		if r==after_end then return #blocks+1 end
		if r~=nil then index=r end

		for i, v in ipairs(blocks) do
			if v.index==index then
				return i
			end
		end
		error("cannot find_index")
	end

	local function process(index, blocks)  -- blocks: list of { ... tokens ..., index=int, len=int, single=bool}  (where index is the original first index of the block)
		-- NOTE: might change the value of blocks
		if index>#commands then
			-- okay done
			return blocks
		end
		local pos, target=commands[index][1], commands[index][2]

		if pos~=nil then
			-- first process the expansion (guess what the result would be after this one step of expansion)
			local i=find_index(blocks, pos)
			local j=find_index(blocks, target)
			assert(i<j)

			blocks[j].single=false  -- this (and some following tokens) becomes an unknown blob
			-- so the algorithm might be over-optimistic, but for simplicity we ignore that case...

			for k=i, j-1 do
				if not blocks[k].single then
					error("unachievable, some token inbetween has unknown length")
				end
			end
		end

		if false then --  debug print code
			prettyprint("======== debug:")
			for i=1, #blocks do
				local b=blocks[i]
				prettyprint(b, "|", b.index, "len=", b.len, "single=", b.single)
			end
			prettyprint("======== /end debug")
		end

		-- then process the single_token_marker
		if commands[index].single_token_marker then
			for _, v in ipairs(commands[index].single_token_marker) do
				local first, len=v[1], v[2]
				local first_block_index=find_index(blocks, first)

				local last_block_index=first_block_index
				local len_so_far=blocks[first_block_index].len
				while len_so_far<len do
					last_block_index=last_block_index+1
					len_so_far=len_so_far+blocks[last_block_index].len
				end

				if len_so_far>len then
					errorx("something is wrong? Maybe there's a label between a single token section, or overlapping single token marker...?")
				end

				local b=blocks[first_block_index]
				for i=first_block_index+1, last_block_index do
					appendto(b, blocks[i])
					b.len=b.len+blocks[i].len
				end
				b.single=true

				blocks=cati(slice(blocks, 1, first_block_index), slice(blocks, last_block_index+1))
			end
		end


		-- pass to next level
		blocks=process(index+1, blocks)

		if pos==nil then return blocks end

		-- insert the expandafters
		local i=find_index(blocks, pos)
		local j=find_index(blocks, target)

		--prettyprint("i=", i, "j=", j)
		assert(i<j)

		local result=slice(blocks, 1, i-1)
		for k=i, j-1 do
			local b=blocks[k]
			result[#result+1]={expandafter, index=b.index, single=true}
			b.index=nil
			result[#result+1]=b
		end
		appendto(result, slice(blocks, j))
		--prettyprint("index=", index, "return", cat(table.unpack(result)))
		return result
	end

	--[[
	main interface for withexpand compilation.

	tokens: tokenlist as usual
	commands: tokenlist (must be real tokens!!!) of the form
		\expandat ...
		\expandatlabel ...

		\onlabel ... \expandat ...
		\after ... \expandat[label] ...
		\before ... \expandat[label] ...

	return a list of tokens.
	]]
	function withexpand_compile(tokens_, commands_)
		reset_local_vars(tokens_)

		tex.runtoks(function()
			token.put_next(cati({bgroup, token.create("withexpandinit")}, commands_, {egroup}))
		end)
		-- TODO for some reason this does not trap

		local blocks={}
		for i, v in ipairs(tokens) do
			if is_label[i] then
				pending_reindex[#pending_reindex+1]=i
			else
				for _, i1 in ipairs(pending_reindex) do
					reindex[i1]=i
				end
				pending_reindex={}

				blocks[#blocks+1]={v, index=i, len=1, single=true}
			end
		end

		for _, i1 in ipairs(pending_reindex) do
			reindex[i1]=after_end
		end

		blocks=process(1, blocks)
		
		return cati(table.unpack(blocks))

		--for _, x in ipairs(commands) do
		--	prettyprint(x[1], x[2])
		--end
	end

	-- debug function
	function replace_expandafter_with_ex(tokens)
		for i, v in ipairs(tokens) do
			if v.csname=="expandafter" then
				tokens[i]=faketoken "ex"
			end
		end
		return tokens
	end
end

function cmd_imperative_run()
	local result=(compile_outer(token.scan_toks()))
	-- brace to get first return value only.

	optimize_pending_definitions()
	if imperative_debug then
		debug_rdef()
	end
	execute_pending_definitions()

	if imperative_debug then
		prettyprint("going to execute", result)
	end
	print_fake_tokenlist(result)
end
