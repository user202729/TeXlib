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
			local ch=string.char(t.mode)
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

F.bgroup=token.create(string.byte "{", 1)
F.egroup=token.create(string.byte "}", 2)
F.paramsign=token.create(string.byte "#", 6)
F.expandafter=token.create "expandafter"
F.iffalseT=token.create "iffalse"
F.fiT=token.create "fi"
assert(expandafter.csname=="expandafter")  -- TODO

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
			if sub[j].tok~=s[offset+j].tok then
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

function F.tl_equal(a, b)
	if #a~=#b then return false end
	for i=1, #a do if a[i].tok~=b[i].tok then return false end end
	return true
end

return F
