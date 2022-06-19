local F={}

function F.slice(t, i, j)
	assert(type(t)=="table")
	if j==nil then j=#t end
	local result={}
	for k=i, j do result[k-i+1]=t[k] end
	return result
end
function F.appendto(result, a)
	assert(type(a)=="table")
	for i=1, #a do result[#result+1]=a[i] end
end

function F.pushtostackfront(stack, ...)  -- stack is represented in reverse order
	local args={...}
	for j=select("#", ...), 1, -1 do
		local a=args[j]
		assert(type(a)=="table")
		for i=#a, 1, -1 do stack[#stack+1]=a[i] end
	end
end

function F.cat(...)
	local result={}
	local args={...}
	for j=1, #args do
		appendto(result, args[j])
	end
	return result
end

function F.cati(result, ...)  -- slight optimization, reuse the first table
	local args={...}
	for j=1, #args do
		appendto(result, args[j])
	end
	return result
end

function F.reverse(t)
	assert(type(t)=="table")
	local result={}
	for i=#t, 1, -1 do result[#result+1]=t[i] end
	return result
end


function F.popstack(stack)
	assert(#stack>0)
	local result=stack[#stack] stack[#stack]=nil
	return result
end

function F.nextstr(s)  -- "" → "a", "a" → "b", ...
	local i=#s
	while s:sub(i, i)=="z" do i=i-1 end
	if i==0 then
		return ("a"):rep(#s+1)
	else
		return s:sub(1, i-1) .. string.char(s:byte(i)+1) .. ("a"):rep(#s-i)
	end
end

function F.errorx(...)
	prettyprint(...)
	local args={...}
	for i=1, select("#", ...) do
		args[i]=tostring(args[i])
	end
	error(table.concat(args))
end

return F
