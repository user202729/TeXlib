for k, v in pairs(require "imperative_util") do
	_ENV[k]=v
end

local F={}
setmetatable(_ENV, {__index=F})

function F.commontokenlistsuffixlen(a, b)
	local i, j=#a, #b
	assert(i==0 or a[i].tok~=nil)
	while i>0 and j>0 and a[i].tok==b[j].tok do i=i-1 j=j-1 end
	return #a-i
end

function F.degree(token)  -- return 1 for {, -1 for }, 0 for anything else
	if token.csname==nil then
		if "left_brace"==token.cmdname then return 1 end
		if "right_brace"==token.cmdname then return -1 end
	end
	return 0
end

function F.commontokenlistbalancedsuffixlen(a, b)
	local l=commontokenlistsuffixlen(a, b)
	local start=#a-l+1
	local d=0
	for j=start, #a do d=d+degree(a[j]) end
	if d==0 then return l end
	for j=start, #a do
		d=d-degree(a[j])
		if d==0 then return #a-j end
	end
end

function F.getbalanced(stack)  -- get the smallest nonzero part that is balanced (might be an explicit space)
	local curDegree=0
	local result={}
	while true do
		local t=popstack(stack)
		result[#result+1]=t
		curDegree=curDegree+degree(t)
		if curDegree==0 then return result end
		if curDegree<0 then error("Extra } while scanning argument in Lua") end
	end
end

function F.getbracegroup(stack)  -- similar to getbalanced, but argument must be a brace group
	local result=getbalanced(stack)
	if #result<=1 then errorx("not a balanced group. stack=", reverse(stack)) end
	return result
end

function F.getbracegroupinside(stack)  -- same as above, but only return the content inside
	local result=getbracegroup(stack)
	return slice(result, 2, #result-1)
end

function F.getuntilbrace(stack)
	local collected={}
	while #stack>0 do
		local t=stack[#stack]
		local d=degree(t)
		if d<0 then error "getuntilbrace hits a }" end
		if d>0 then return collected end
		stack[#stack]=nil
		collected[#collected+1]=t
	end
	error "getuntilbrace cannot find a {"
end

function F.is_space(token)
	return token.csname==nil and token.cmdname=="spacer" and token.mode==0x20
end

assert(string.byte "*"==42)
function F.is_star(token)  -- ignore catcode
	return token.csname==nil and token.mode==42
end
--F.star_token=token.create(42, 12)  -- 12 is catcode other

function F.get_optional_star(stack)  -- return the star token or nil
	if is_star(stack[#stack]) then
		return popstack(stack)
	end
	return nil
end

function F.get_arg(stack)  -- scan for an (undelimited) argument the same way TeX does. Explicit spaces are skipped, outer brace are removed.
	local result=getbalanced(stack)
	if #result==1 then
		if is_space(result[1]) then
			return get_arg(stack)
		end
		return result
	else
		return slice(result, 2, #result-1)
	end
end

function F.faketoken(csname)
	return {csname=csname, tok="faketoken-"..csname, cmdname=""}
end

function F.makefaketoken(t)
	if type(t)=="table" then return t end
	return {
		_originaltoken=t,
		command=t.command,
		cmdname=t.cmdname,
		csname=t.csname,
		id=t.id,
		tok=t.tok,
		active=t.active,
		expandable=t.expandable,
		protected=t.protected,
		mode=t.mode,
		index=t.index,
	}
end

function F.makerealtoken(t)
	if type(t)=="userdata" then return t end
	assert(t._originaltoken)
	return t._originaltoken
end

local cmdname_to_catcode={
	left_brace="1",
	right_brace="2",
	math_shift="3",
	tab_mark="4",
	mac_param="6",
	sup_mark="7",
	sub_mark="8",
	spacer="A",
	letter="B",
	other_char="C",
}

function F.get_tlreprx(tokens)
	local s={}
	for _, t in ipairs(tokens) do
		if t.csname==nil then
			local ch=utf8.char(t.mode)
			local cat=cmdname_to_catcode[t.cmdname]

			if t.cmdname=="mac_param" then s[#s+1]="6#" end  -- not necessary for e-expansion, only for x-expansion

			if ch==' ' then
				if t.cmdname=="spacer" then
					s[#s+1]="s"
				else
					s[#s+1]="S"..cat
				end
			else
				s[#s+1]=cat..ch
			end
		elseif t.active then
			if t.csname==" " then
				s[#s+1]="SD"
			else
				s[#s+1]="D"..t.csname
			end
		elseif t.tok==prettyprint_frozenrelaxtok then  -- TODO requires prettyprint library
			s[#s+1]="R"
		else
			assert(not t.csname:find("/", 1, true))
			s[#s+1]="0"..t.csname.."/"
		end
	end
	s[#s+1]="."
	return table.concat(s)
end

function F.print_fake_tokenlist(t)
	tex.tprint(
		{-1, [[\csname __process_all\endcsname{]]},  -- assume this is safe in current catcode regime (which it most usually is...)
		{-2, get_tlreprx(t)},
		{-1, [[}]]}
	)
end

local function token_create(s)
	assert(type(s)=="string")
	local result=token.create(s)
	assert(result.csname==s)
	return result
end

F.bgroup=token.create(string.byte "{", 1)
F.egroup=token.create(string.byte "}", 2)
F.paramsign=token.create(string.byte "#", 6)
F.space_token=token.create(string.byte " ", 10)
F.star_token=token.create(string.byte "*", 12)
F.exclam_token=token.create(string.byte "!", 12)
F.expandafter=token_create "expandafter"
F.exp_end=token_create "exp_end:"
F.iffalseT=token_create "iffalse"
F.fiT=token_create "fi"

function F.wrapinbracegroup(t)
	return cat({bgroup}, t, {egroup})
end

function F.optionalwrapinbracegroup(t)
	if #t==1 then return t end
	return wrapinbracegroup(t)
end

local randomlabelname=""
function F.randomlabel()  -- return a unique faketoken object
	randomlabelname=nextstr(randomlabelname)
	return faketoken("labelzz"..randomlabelname)
end

local randomvarname=""
function F.randomvar()  -- return a unique faketoken object
	randomvarname=nextstr(randomvarname)
	return faketoken("varzz"..randomvarname)
end


function F.is_paramsign(token)
	return token.csname==nil and token.cmdname=="mac_param"
end

function F.get_paramnumber(token)  -- return 1-9 if it's a param token, else return nil
	if token.csname==nil and 0x31<=token.mode and token.mode<=0x39 then
		return token.mode-0x30
	end
	return nil
end

-- absorb something like '#x' from the top of the stack and return x as a token.
function F.getvarname(stack)
	local paramsign=popstack(stack)   -- the '#' token
	assert(is_paramsign(paramsign))  -- we don't check the char code, only catcode and is-explicit is enough
	local varname=popstack(stack)
	return varname
end

function F.find_subsequence(sub, s)  -- return the only offset (0-indexed even though this is Lua), or -1 if not found, or -2 if there are multiple
	local result=-1
	for offset=0, #s-#sub do
		local okay=true
		for j=1, #sub do
			if not (
				sub[j].tok==s[offset+j].tok or
				(  -- handle faketoken
					(not sub[j].active) and
					(not s[offset+j].active) and
					sub[j].csname~=nil and
					sub[j].csname==s[offset+j].csname  -- note that this does not distinguish between the null control sequence and '\cC{\\csname\\endcsname}'
				)
			) then
				okay=false
				break
			end
		end
		if okay then
			if result>=0 then return -2 end  -- multiple occurrences
			result=offset
		end
	end
	--prettyprint( "sub=", sub, "s=", s, "result=", result)
	return result  -- might be 0
end

function F.find_subsequence_checked(sub, s)
	local result=find_subsequence(sub, s)
	if result==-1 then errorx("cannot find ", sub, " in ", s)  end
	if result==-2 then errorx("cannot uniquely find ", sub, " in ", s)  end
	return result
end

function F.simple_args(paramtext)  -- return whether paramtext has the form \f #1 #2 ...
	assert(paramtext[1].csname)
	if #paramtext%2==0 then return false end
	for i=2, #paramtext, 2 do if not is_paramsign(paramtext[i]) then return false end end
	for i=3, #paramtext, 2 do
		if is_paramsign(paramtext[i]) then return false end  -- cannot be ##
		assert(paramtext[i].mode-0x30==i//2)  -- that they're in the correct order
	end
	return true
end

function F.have_double_arg_use(replacementtext)  -- return whether some arg is used more than once in replacementtext
	local i, n=1, #replacementtext
	local seen={}
	while i<=n do
		if is_paramsign(replacementtext[i]) then
			assert(i+1<=n)
			if not is_paramsign(replacementtext[i+1]) then
				local paramnumber=get_paramnumber(replacementtext[i+1])
				assert(paramnumber)
				if seen[paramnumber] then return true end
				seen[paramnumber]=true
			end
			i=i+2
		else
			i=i+1
		end
	end
	return false
end

-- these are used as the values in the `need` and `produce` table

-- e.g. `need={[a.tok]=argtype.normal, [b.tok]=argtype.Ntype}` means the statement
-- needs a and b, and b is guaranteed to be N-type (single token, not explicit space)

local function Ntype_get_nextvalue(token)  -- TODO issue here. if initial of matchrm sequence is delimiter which happens to be equal to the token itself there would be a problem
	return {paramsign, token}
end

local function normal_get_nextvalue(token)
	return {bgroup, paramsign, token, egroup}
end

local function star_delimited_get_nextvalue(token)
	return {paramsign, token, star_token}
end

local function exclam_delimited_get_nextvalue(token)
	return {paramsign, token, exclam_token}
end

local function singletoken_get_expandafter_sequence(token)
	return {expandafter, paramsign, token}
end

local function standard_arg_paramtext(token)
	return {paramsign, token}
end

local function star_delimited_arg_paramtext(token)
	return {paramsign, token, star_token}
end

local function exclam_delimited_arg_paramtext(token)
	return {paramsign, token, exclam_token}
end


F.argtype={
	deleted={  -- "bottom type"
		specificity=0,
	},
	normal={
		get_nextvalue=normal_get_nextvalue,
		paramtext=standard_arg_paramtext,
		specificity=1,  -- larger value → more specific (normal is the most general)
	},
	single_token={
		get_nextvalue=normal_get_nextvalue,
		get_expandafter_sequence=singletoken_get_expandafter_sequence,
		paramtext=standard_arg_paramtext,
		specificity=2,
	},
	Ntype={
		--get_nextvalue=Ntype_get_nextvalue,
		get_nextvalue=normal_get_nextvalue,
		get_expandafter_sequence=singletoken_get_expandafter_sequence,
		paramtext=standard_arg_paramtext,
		specificity=3,
	},
	-- an argument is expforward_chain if r-expansion of <arg> <tokenlist> = <arg> + r-expansion of <tokenlist>
	expforward_chain={
		get_nextvalue=star_delimited_get_nextvalue,
		get_expandafter_sequence=function(token)
			return {faketoken "exp:w", paramsign, token, expandafter, exp_end, expandafter, star_token}
		end,
		paramtext=star_delimited_arg_paramtext,
		specificity=4,
	},
	number={
		--get_nextvalue=star_delimited_get_nextvalue,
		--get_expandafter_sequence=function(token)
		--	return {faketoken "number", paramsign, token, expandafter, star_token}
		--end,
		--paramtext=star_delimited_arg_paramtext,

		get_nextvalue=normal_get_nextvalue,
		get_expandafter_sequence=function(token)
			return {expandafter, bgroup, faketoken "number", paramsign, token, expandafter, egroup}
		end,
		paramtext=standard_arg_paramtext,

		specificity=5,
	},
	dim={
		get_nextvalue=exclam_delimited_get_nextvalue,
		get_expandafter_sequence=function(token)
			return {faketoken "the", faketoken "dimexpr", paramsign, token, expandafter, exclam_token}
		end,
		paramtext=exclam_delimited_arg_paramtext,
		specificity=6,
	},
	empty_set={
		specificity=7,
	}
}

--[[
local function inspect2(...)
	local args={...}
	for i=1, select("#", ...) do
		inspect(args[i])
	end
end
]]

for name, t in pairs(argtype) do
	t.debugname=name
	t.is_a={[t]=true}
end


-- Ntype.normal means all Ntype are normal
-- etc.

local inherit_frozen={}
local function inherit(a, b)
	assert(a.specificity>b.specificity)
	inherit_frozen[b]=true assert(not inherit_frozen[a])  --some simple checking of the order below
	for c, _ in pairs(b.is_a) do
		a.is_a[c]=true  -- inheritance is transitive
	end
end


-- note about the ordering, upper ones must be specified before lower ones.
-- everything must be subtype of normal.
inherit(argtype.normal, argtype.deleted)

inherit(argtype.single_token, argtype.normal)
inherit(argtype.Ntype, argtype.single_token)  -- for example this line means a N-type arg is a single_token arg
inherit(argtype.expforward_chain, argtype.normal)
inherit(argtype.number, argtype.normal)
inherit(argtype.dim, argtype.normal)

inherit(argtype.empty_set, argtype.normal)
inherit(argtype.empty_set, argtype.single_token)
inherit(argtype.empty_set, argtype.Ntype)
inherit(argtype.empty_set, argtype.expforward_chain)
inherit(argtype.empty_set, argtype.number)
inherit(argtype.empty_set, argtype.dim)


-- essentially inherit(A, B) means "the set of possible values of A is a subset of possible values of B"
-- and "normal" is the "everything" set (must be balanced however), "deleted" is the everything set plus the [INVALID] value.
-- Any operation on the [INVALID] value must give error.
--
-- unlike the normal definition of bottom type (being the empty set), this one is more convenient I think...?
--
--
-- the type "empty_set" represents the "real" bottom type. This is just for convenience i.e. it's an identity in argtype_either operation


-- just checking
assert(argtype.Ntype.is_a[argtype.single_token])
assert(argtype.Ntype.is_a[argtype.normal])



-- create this table. Description below
F.argtype_either={}
F.argtype_both={}
for _, a in pairs(argtype) do
	argtype_either[a]={}
	argtype_both[a]={}
	for _, b in pairs(argtype) do
		local result_either=argtype.deleted  -- the most general type
		for _, c in pairs(argtype) do
			if a.is_a[c] and b.is_a[c] and c.is_a[result_either] then
				result_either=c  -- only update if c.is_a[result_either] i.e. let result_either be the most specific type that is a superset of both a and b
			end
		end
		argtype_either[a][b]=result_either
		if a.specificity<b.specificity then
			argtype_both[a][b]=b
		else
			argtype_both[a][b]=a
		end
	end
end

assert(argtype_either[argtype.Ntype][argtype.single_token]==argtype.single_token)  -- i.e. if it's either Ntype or single_token, it's guaranteed to be single_token

assert(argtype_both[argtype.Ntype][argtype.single_token]==argtype.Ntype)  -- i.e. if it's both Ntype or single_token, it's guaranteed to be Ntype

assert(argtype_either[argtype.deleted][argtype.Ntype]==argtype.deleted)
assert(argtype_either[argtype.deleted][argtype.deleted]==argtype.deleted)

assert(argtype_either[argtype.empty_set][argtype.Ntype]==argtype.Ntype)
assert(argtype_either[argtype.empty_set][argtype.deleted]==argtype.deleted)
assert(argtype_either[argtype.empty_set][argtype.normal]==argtype.normal)



-- attempt to match args.
-- If returns true, the stack is guaranteed to be in clean state (i.e. with X args removed),
-- if return false, no guarantee (on the resulting state of the stack)

-- caller_param_tag: a "param_tag" table, see namedef_to_macrodef() function documentation
-- target_paramtext: ...
-- caller_replacementtext: ...
--
-- return (matched_args, stack) if matches, else return nil
-- note that target_replacementtext is not given
--
--
-- it's a bit hard to explain. For example:
--
-- caller_param_tag = {1=argtype.normal, 2=argtype.Ntype}
-- caller replacement text = tokenlist '{#1}#2abc'
-- target_paramtext = tokenlist '#1#2'
--
-- → matches
-- return
--    matched_args={1='#1', 2='#2'}
--    stack=reverse(tokenlist 'abc')  i.e. the remaining part, as a stack
--
-- matched_args can be used in the argument of substitute_replacementtext() below.
function F.try_grab_args(caller_param_tag, target_paramtext, caller_replacementtext)
	if not simple_args(target_paramtext) then return nil end

	local stack=reverse(caller_replacementtext)

	local matched_args={}
	for _=1, #target_paramtext//2 do
		-- attempt to absorb an undelimited argument
		while #stack>0 and is_space(stack[#stack]) do
			pop_stack()
		end
		if #stack==0 then return nil end  -- maybe target is a matchrm that looks ahead

		local t=popstack(stack)
		local d=degree(t)
		if d==1 then
			-- it's an bgroup
			stack[#stack+1]=t
			matched_args[#matched_args+1]=getbracegroupinside(stack)
		elseif d==-1 then
			errorx("} seen while scanning argument of \\"..target.csname)
		else
			assert(d==0)
			if is_paramsign(t) then
				local u=popstack(stack)
				matched_args[#matched_args+1]={t, u}  -- guess
				if not is_paramsign(u) then  -- it might be #1 that expands to something unknown...?
					local paramnumber=get_paramnumber(u)
					assert(paramnumber)
					if not caller_param_tag[paramnumber].is_a[argtype.Ntype] then
						return nil
					end
				end
			else
				-- it's a simple token, will be grabbed
				matched_args[#matched_args+1]={t}
			end
		end
	end
	return matched_args, stack
end

-- note that the key of args here are Lua number 1 → 9.
function F.substitute_replacementtext(replacementtext, args)
	local i, n=1, #replacementtext
	local result={}
	while i<=n do
		if is_paramsign(replacementtext[i]) then
			assert(i+1<=n)
			if is_paramsign(replacementtext[i+1]) then
				result[#result+1]=replacementtext[i]
				result[#result+1]=replacementtext[i+1]
			else
				local paramnumber=get_paramnumber(replacementtext[i+1])
				appendto(result, args[paramnumber])
			end
			i=i+2
		else
			result[#result+1]=replacementtext[i]
			i=i+1
		end
	end
	return result
end

-- for this one the key of args is .tok value instead
function F.substitute_replacementtext_symbolic(replacementtext, args)
	local i, n=1, #replacementtext
	local result={}
	while i<=n do
		if is_paramsign(replacementtext[i]) then
			assert(i+1<=n)
			if is_paramsign(replacementtext[i+1]) then
				result[#result+1]=replacementtext[i]
				result[#result+1]=replacementtext[i+1]
			else
				appendto(result, args[replacementtext[i+1].tok])
			end
			i=i+2
		else
			result[#result+1]=replacementtext[i]
			i=i+1
		end
	end
	return result
end

function F.tl_equal(a, b)
	if #a~=#b then return false end
	for i=1, #a do if a[i].tok~=b[i].tok then return false end end
	return true
end

return F
