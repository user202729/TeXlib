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
	curDegree=0
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
	return token.csname==nil and token.cmdname=="spacer"
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

function F.get_tlreprx(tokens)
	local s={}
	for _, t in ipairs(tokens) do
		if t.csname==nil then
			if t.cmdname=="spacer" and t.mode==32 then
				s[#s+1]="1"
			elseif t.cmdname=="mac_param" then
				s[#s+1]="0#.60"..string.char(t.mode)..".6"
			else
				s[#s+1]="0"..string.char(t.mode).."."..({
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
				})[t.cmdname]
			end
		elseif t.active then
			s[#s+1]="0"..t.csname..".D"
		else
			s[#s+1]="2"..t.csname..string.char(1)
		end
	end
	s[#s+1]="3"
	return table.concat(s)
end

function F.print_fake_tokenlist(t)
	tex.tprint(
		{-1, [[\csname use:x\endcsname{]]},  -- assume this is safe in current catcode regime (which it most usually is...)
		{-2, get_tlreprx(t)},
		{-1, [[}]]}
	)
end

F.bgroup=token.create(string.byte "{", 1)
F.egroup=token.create(string.byte "}", 2)
F.paramsign=token.create(string.byte "#", 6)
F.expandafter=token.create "expandafter"
assert(expandafter.csname=="expandafter")

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

return F
