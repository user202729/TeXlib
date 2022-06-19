for k, v in pairs(require "imperative_tlutil") do
	_ENV[k]=v
end

local function getvarsraw(tokenlist)  -- for example if tokenlist='#x 123 #y' return '{[x.tok]=true, [y.tok]=true}'
	-- where x.tok is the .tok value of the token x
	local result={}
	for i=1, #tokenlist-1 do  -- if the last one is mac_param then just assume it's trailing # for match-until-'{'
		local v=tokenlist[i]
		if is_paramsign(v) then
			result[tokenlist[i+1].tok]=true
		end
	end
	return result
end

local function getvarsexpr(expr)  -- TODO when support operateon, need to exclude internal-only vars
	return getvarsraw(expr)
end

local Ntypemark={}  -- this is used as a mark in `need` and `produce` table
-- e.g. `need={[a.tok]=true, [b.tok]=Ntypemark}` means the statement
-- needs a and b, and b is guaranteed to be a single token

local function namedef_to_macrodef(paramtext, replacementtext)  -- paramtext&replacementtext are tokenlists
	-- operate in-place.
	local used=0
	local tok_to_number_token={}  -- e.g. a.tok → 1, b.tok → 2, etc.
	for i=1, #paramtext-1 do
		local v=paramtext[i]
		if is_paramsign(v) then
			used=used+1
			if used>=10 then
				error("too many parameters")
			end
			local t=token.create(48+used, 12)
			assert(not is_paramsign(paramtext[i+1]))
			tok_to_number_token[paramtext[i+1].tok]=t
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
			assert(#s>0)
			lastlinenumber=tonumber(s)
		else
			t=makefaketoken(t)
			t._linenumber=lastlinenumber
			result[#result+1]=t
		end
		i=i+1
	end
	return result
end

local pending_definitions={}  -- list of {paramtext, replacementtext}

local function finalize_generate_code(paramtext, replacementtext)  -- the macro itself is included in paramtext
	paramtext=slice(paramtext, 1)
	replacementtext=slice(replacementtext, 1)
	--prettyprint("finalize:", paramtext, "→", replacementtext)
	namedef_to_macrodef(paramtext, replacementtext)
	for _, kv in pairs(pending_definitions) do
		if kv[1][1].csname==paramtext[1].csname and kv[1][1].active==paramtext[1].active then
			errorx("duplicate definition of ", paramtext[1])  -- not very efficient but okay
		end
	end
	table.insert(pending_definitions, {paramtext, replacementtext})
end

local function generic_compile_code(functionname, body, passcontrol)  -- functionname: single token, body: tokenlist (possibly with _linenumber info added)
	-- passcontrol: tokenlist consist of tokens that will be prepended when this function returns

	local tokenfromtok_t={} -- actually this could be eliminated, but it's convenient
	for _, t in ipairs(body) do tokenfromtok_t[t.tok]=t end

	local function tokenfromtok(tok)
		local t=tokenfromtok_t[tok]
		assert(t~=nil)
		return t
	end

	local labelfunctionend=randomlabel()
	body=cati(body, {faketoken "label", labelfunctionend})

	------ very special preprocessor (TODO keep linenumbers)

	local stack=reverse(body)
	body={}
	local translator={
		Iexpandtobgroup=function()
			appendto(body, {expandafter, bgroup, iffalseT, egroup, fiT})
		end,
		Iexpandtoegroup=function()
			appendto(body, {iffalseT, bgroup, fiT, egroup})
		end,
		Iremovebgroup=function()
			local bgroup_=popstack(stack)
			if bgroup.tok~=bgroup_.tok then
				errorx("Iremovebgroup followed by ", bgroup_)
			end
			appendto(body, {iffalseT, bgroup_, fiT})
		end,
		Iremoveegroup=function()
			local egroup_=popstack(stack)
			if egroup.tok~=egroup_.tok then
				errorx("Iremoveegroup followed by ", egroup_)
			end
			appendto(body, {iffalseT, egroup_, fiT})
		end,
	}
	while #stack>0 do
		local t=popstack(stack)
		local handler=translator[t.csname]
		if handler then
			handler()
		else
			body[#body+1]=t
		end
	end

	------ resume to normal processing
	stack=reverse(body)

	local statements={}

	local function param_from_need(needsequence)  -- takes tokenfromtok implicitly
		local t={}
		for _, kv in ipairs(needsequence) do
			t[#t+1]=paramsign
			t[#t+1]=tokenfromtok(kv[1])
		end
		return t
	end

	local function standard_paramtext(statement)
		local t={statement.caller}
		appendto(t, param_from_need(statement.needsequence))
		return t
	end

	local function standard_nextvalue(next_statement)
		local nextvalue={}
		for k, v in pairs(next_statement.need) do
			if v==Ntypemark then
				nextvalue[k]={paramsign, tokenfromtok(k)}
			else
				nextvalue[k]={bgroup, paramsign, tokenfromtok(k), egroup}
			end
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
	
	local function generate_code_prepare(statement)  -- return paramtext, replacementtext assume the operation is no-op
		local paramtext=standard_paramtext(statement)
		local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
		return paramtext, replacementtext
	end


	local function generate_code_noop(statement)  -- well...
		finalize_generate_code(generate_code_prepare(statement))
	end

	local lastlinenumber=0

	local function add_statement(statement)
		if #statements==0 then
			statement.caller=functionname
		else
			statement.caller=next_st(lastlinenumber)
			statement.caller._internal_function=true  -- i.e. it's possible to eliminate this function, "not public API"
		end
		statements[#statements+1]=statement
	end

	local function compile_backquote(tokens, is_mark)  -- tokens: list of tokens, is_mark: function takes a token and return bool
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

	local handlers={
		----------------------------------------------------------------------------
		-- the "primitives"

		matchrm=function()
			local group=getbracegroupinside(stack)
			for _, v in ipairs(group) do assert(degree(v)==0) end
			add_statement {
				debug=cati({faketoken "matchrm"}, wrapinbracegroup(group)),
				produce=getvarsraw(group),
				generate_code=function(statement)
					local paramtext, replacementtext=generate_code_prepare(statement)
					paramtext=cat(paramtext, group)
					finalize_generate_code(paramtext, replacementtext)
				end,
			}
		end,

		putnext=function()
			local group=getbracegroupinside(stack)
			add_statement {
				debug=cati({faketoken "putnext"}, wrapinbracegroup(group)),
				need=getvarsexpr(group),
				generate_code=function(statement)
					local paramtext, replacementtext=generate_code_prepare(statement)
					replacementtext=cat(replacementtext, group)
					finalize_generate_code(paramtext, replacementtext)
				end,
			}
		end,

		expandonce=function()
			add_statement {
				debug={faketoken "expandonce"},
				generate_code=function(statement)
					local paramtext, replacementtext=generate_code_prepare(statement)

					local n=statement.nextindex
					replacementtext={expandafter, statements[n].caller}

					for _, kv in ipairs(statements[n].needsequence) do
						if kv[2]~=Ntypemark then
							error("expandonce but some parameters are not single token")
						end
						appendto(replacementtext, {expandafter, paramsign, tokenfromtok(kv[1])})
					end
					finalize_generate_code(paramtext, replacementtext)
				end,
			}
		end,

		assertisNtype=function()
			local varname=getvarname(stack)
			add_statement {
				debug={faketoken "assertisNtype", varname},
				need={[varname.tok]=true},
				produce={[varname.tok]=Ntypemark},
				generate_code=generate_code_noop,
			}
		end,

		conditionalgoto=function()
			local star=get_optional_star(stack)
			local conditional=getbracegroupinside(stack)
			local targetiftrue=popstack(stack)
			add_statement {
				debug=cati({faketoken "conditionalgoto"}, wrapinbracegroup(conditional), {targetiftrue}),
				conditionalgoto=targetiftrue,
				need=getvarsexpr(conditional),
				generate_code=function(statement)
					local paramtext=standard_paramtext(statement)
					local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
					local replacementtext2=standard_replacementtext(statements[statement.conditionalgoto], standard_nextvalue(statements[statement.conditionalgoto]))
					if star then  -- conditional might peek, don't eliminate common suffix
						finalize_generate_code(paramtext, cat(
							conditional,
							optionalwrapinbracegroup(replacementtext2),
							optionalwrapinbracegroup(replacementtext)
						))
					else
						local l=commontokenlistbalancedsuffixlen(replacementtext, replacementtext2)
						finalize_generate_code(paramtext, cat(
							conditional,
							optionalwrapinbracegroup(slice(replacementtext2, 1, #replacementtext2-l)),
							optionalwrapinbracegroup(slice(replacementtext, 1, #replacementtext-l)),
							slice(replacementtext, #replacementtext-l+1, #replacementtext)
						))
					end
				end,
			}
		end,

		label=function()
			local labelname=popstack(stack)
			add_statement {
				debug={faketoken "label", labelname},
				label=labelname,
				generate_code=generate_code_noop,
			}
		end,

		["goto"]=function()
			local labelname=popstack(stack)
			add_statement {
				debug={faketoken "goto", labelname},
				goto_=labelname,
				generate_code=generate_code_noop,
			}
		end,

		assign=function()
			local varname=getvarname(stack)
			local content=getbracegroup(stack)
			add_statement {
				debug=cati({faketoken "assign", varname}, content),
				need=getvarsexpr(content),
				produce={[varname.tok]=true},
				generate_code=function(statement)
					local paramtext=standard_paramtext(statement)
					local nextvalue=standard_nextvalue(statement)
					nextvalue[varname.tok]=content
					local replacementtext=standard_replacementtext(statements[statement.nextindex], nextvalue)
					finalize_generate_code(paramtext, replacementtext)
				end,
			}
		end,

		assigno=function()  -- assigno #x {123}
			local varname=getvarname(stack)
			local content=getbracegroup(stack)
			add_statement {
				debug=cati({faketoken "assigno", varname}, content),
				need=getvarsexpr(content),
				assigno_tok=varname.tok,
				produce={[varname.tok]=true},
				generate_code=function(statement)
					local paramtext=standard_paramtext(statement)
					local nextvalue=standard_nextvalue(statement)
					local next_statement=statements[statement.nextindex]
					assert(next_statement.needsequence[1][1]==varname.tok)
					nextvalue[varname.tok]=content
					local replacementtext=standard_replacementtext(next_statement, nextvalue)
					finalize_generate_code(paramtext, cati(
						{expandafter, replacementtext[1], expandafter},
						slice(replacementtext, 2)
						))
				end,
			}
		end,

		expcall=function()
			local content=getbracegroupinside(stack)
			add_statement {
				debug=cati({faketoken "expcall"}, content),
				need=getvarsexpr(content),
				generate_code=function(statement)
					local paramtext=standard_paramtext(statement)
					local replacementtext=standard_replacementtext(statements[statement.nextindex], standard_nextvalue(statements[statement.nextindex]))
					finalize_generate_code(paramtext, cat(content, replacementtext))
				end,
			}
		end,

		----------------------------------------------------------------------------
		-- macro-like (transform the code itself)

		["return"]=function()
			local group=getbracegroup(stack)
			pushtostackfront(stack, 
				{faketoken "putnext"}, group,
				{faketoken "goto", labelfunctionend}
			)
		end,
		
		assignr=function()  -- \assignr #x {\some function that is rdef-ed}
			local varname=getvarname(stack)
			local content=getbracegroupinside(stack)
			pushtostackfront(stack, 
				{faketoken "assigno", paramsign, varname, bgroup, faketoken "exp:w"}, content, {egroup}
			)
		end,

		backquote=function()  -- lisp backquote-like
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

		assignoperate=function()  -- \assignoperate #x {#x #y} {\matchrm...}
			local varname=getvarname(stack)
			local content=getbracegroupinside(stack)
			local operations=getbracegroupinside(stack)

			local localfn=next_st(lastlinenumber)
			localfn._internal_function=true
			generic_compile_code(localfn, operations, {faketoken "exp_end:"})

			pushtostackfront(stack, 
				{faketoken "assigno", paramsign, varname, bgroup, faketoken "exp:w", localfn}, 
				content,
				{egroup}
			)
		end,

		conditional=function()
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

		["while"]=function()
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

		putnextwithexpand=function()
			local tokens=getbracegroupinside(stack)
			local commands=getbracegroupinside(stack)
			for i, v in pairs(tokens) do tokens[i]=makerealtoken(v) end
			for i, v in pairs(commands) do commands[i]=makerealtoken(v) end
			pushtostackfront(stack, {faketoken "putnext"}, wrapinbracegroup(withexpand_compile(tokens, commands)))
		end,

		rcall=function()
			local tokens=getbracegroupinside(stack)
			pushtostackfront(stack, {faketoken "putnext",
				bgroup, faketoken "romannumeral"}, tokens, {egroup,
				faketoken "expandonce"})
		end,

		pretty=function()
			local content=getbracegroupinside(stack)
			pushtostackfront(stack, {faketoken "expcall",
				bgroup, faketoken "prettye:n", bgroup, faketoken("[L"..lastlinenumber.."]:")}, content, {egroup, egroup})
		end,

		prettyw=function()
			pushtostackfront(stack, {faketoken "expcall", bgroup,
				faketoken "prettye:nw", faketoken("[L"..lastlinenumber.."]:"),
			egroup})
		end,
	}

	while #stack>0 do
		local t=popstack(stack)
		if t._linenumber~=nil then
			lastlinenumber=t._linenumber
		end
		if t.csname==nil or handlers[t.csname]==nil then
			errorx("invalid token seen: (", t, ") on line ", lastlinenumber)
		end
		handlers[t.csname]()
	end


	local labelpos={}  -- [label.tok] -> index
	for i, v in ipairs(statements) do
		if v.label then
			labelpos[v.label.tok]=i
		end
	end

	for i, v in ipairs(statements) do
		v.comefrom={}
		if v.need==nil then v.need={} end
		if v.produce==nil then v.produce={} end
	end

	for i=1, #statements-1 do
		v=statements[i]

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

	.need: set of var tok needed by that statement
	.produce: ↑ set of var tok produced by that statement

	.caller: some random token generated for this line of code...

	other primitive-specific things

	next step: propagate the `need` values
	]]

	local function propagate(i, tok)
		local v=statements[i]
		assert(v.need[tok])
		for _, j in pairs(v.comefrom) do
			if not statements[j].need[tok] and not statements[j].produce[tok] then
				statements[j].need[tok]=true
				propagate(j, tok)
			end
		end
	end
	for i=1, #statements-1 do
		for k, _ in pairs(statements[i].need) do
			propagate(i, k)
		end
	end

	-- then, propagate the `produce` values
	local function propagate2(j, tok)
		-- here some statement before j produces tok as single token.
		-- check if j also produces tok as single token.
		if statements[j].produce[tok]~=nil or statements[j].need[tok]==nil then
			return
		end


		local v=statements[j]
		assert(#v.comefrom>0)

		local okay=true
		for _, k in pairs(v.comefrom) do
			if statements[k].produce[tok]~=Ntypemark then
				okay=false
				break
			end
		end

		if okay then
			assert(v.need[tok]==true)
			v.need[tok]=Ntypemark
			v.produce[tok]=Ntypemark
			propagate(j, tok)
		end
	end

	local function propagate(i, tok)
		-- here i produces tok as single token. Propagate it to j where i goes to j.
		local v=statements[i]
		assert(v.produce[tok]==Ntypemark)
		if v.nextindex~=nil then
			propagate2(v.nextindex, tok)
		end
		if v.conditionalgoto~=nil then
			propagate2(v.conditionalgoto, tok)
		end
	end

	for i=1, #statements-1 do
		for k, v in pairs(statements[i].produce) do
			if v==Ntypemark then
				propagate(i, k)
			end
		end
	end



	-- then, convert `need` table to indexed table (fixed order)
	for _, v in ipairs(statements) do
		local n={}
		for var_tok, var_property in pairs(v.need) do
			-- var_tok: .tok value
			-- var_property: for example Ntypemark
			n[#n+1]={var_tok, var_property}
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
				n[1], n[len+1]={assigno_tok, true}, n[1]
			end

			assert(#n>=old)
		end
	end

	local function debugprintstatements()
		prettyprint "========"
		for i, v in ipairs(statements) do

			s="need="
			if v.need then
				for _, kv in ipairs(v.needsequence) do
					local k, v=kv[1], kv[2]
				--for k, v in pairs(v.need) do
					s=s..tostring(k)
					if w==Ntypemark then s=s.."^" end
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

	--debugprintstatements()

	-- now, generate code...
	for i=1, #statements-1 do
		if statements[i].generate_code then --TODO everything must have handler
			local success, val=xpcall(function()
				statements[i]:generate_code()
			end, debug.traceback)
			if not success then
				debugprintstatements()
				errorx(
					"while processing statement "..i..":\n\n\n"
					.. "======== old traceback start ========\n"
					.. tostring(val)
					.. "\n======== old traceback end ========\n\n\n")
			end
		end
	end
	assert(#statements>0)
	assert(#statements[#statements].needsequence==0)
	finalize_generate_code({statements[#statements].caller}, passcontrol)


	
end

function generic_def_call(passcontrol)
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

	generic_compile_code(functionname, body, passcontrol)
end

function rdef_call()
	generic_def_call({faketoken "exp_end:"})
end

function zdef_call()
	generic_def_call({})
end

function debug_rdef()
	for _, pr in ipairs(pending_definitions) do
		prettyprint(pr[1], "→", pr[2])
	end
end

local function get_execute_pending_definitions_tl(pending_definitions)
	local result={}
	for _, pr in ipairs(pending_definitions) do
		result=cati(result, {faketoken "def"}, pr[1], wrapinbracegroup(pr[2]))
	end
	return result
end

function debug_rdef2()
	print()
	print()
	print()
	print(get_tlreprx(get_execute_pending_definitions_tl(pending_definitions)))
	print()
	print()
	print()
end

function execute_pending_definitions()
	print_fake_tokenlist(get_execute_pending_definitions_tl(pending_definitions))
	pending_definitions={}
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
		local offset=find_subsequence(sub, tokens)
		if offset<0 then errorx("cannot find", sub, "in", tokens)  end
		for j=1, #sub do
			if is_label[offset+j]==true then
				errorx("index "..(offset+j).." was previously marked as label in ", tokens, "token at index=", tokens[offset+j])
			end
			is_label[offset+j]=false
		end
		return offset+1
	end

	local function label_index(label)
		local offset=find_subsequence(label, tokens)
		if offset<0 then errorx("cannot find", label, "in", tokens) end
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
			prettyprint("expansion argument must be after expansion source")
			error()
		end
		if index1<last_index1 then
			prettyprint("commands must be listed in increasing left endpoint order")
			error()
		end
		last_index1=index1
		commands[#commands+1]={index1, index2}
	end

	local function add_single_token_marker(first, len)
		if #commands==0 then
			commands[1]={}
		end
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
		end
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

		-- then process the single_token_marker
		if commands[index].single_token_marker then
			for _, v in ipairs(commands[index].single_token_marker) do
				local first, len=v[1], v[2]
				first=find_index(blocks, first)
				local last
				if blocks[#blocks].index+blocks[#blocks].len==first+len then
					last=#blocks
				else
					last=find_index(blocks, first+len)-1  -- TODO is this really safe...??
				end

				local b=blocks[first]
				for i=first+1, last do
					appendto(b, blocks[i])
					b.len=b.len+blocks[i].len
				end
				b.single=true

				blocks=cati(slice(blocks, 1, first), slice(blocks, last+1))
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
end
