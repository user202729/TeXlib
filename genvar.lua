#!/bin/lua

--[[
Provides a Lua function, that takes a string, tokenize it under expl3 regime (roughly speaking),
output a string consist of generate-variant statements.
(excluding the original code)

Note: not completely accurate (for example this will also include things that looks like control sequences in comments)
]]
do

local parent={
c="N",

o="n",
V="n",
v="n",
f="n",
e="n",
x="n",

N="N",
n="n",
T="T",
F="F",
p="p",
}


return function(s)
	local variants={}
	for name, spec in s:gmatch "\\([A-Za-z_]+):([A-Za-z_:]*)" do
		local base=""
		for c in spec:gmatch "." do
			local p=parent[c]
			if p==nil then
				base=nil
				break
			end
			base=base..p
		end
		if base~=nil and base~=spec then
			local fullname=name..":"..base
			if variants[fullname]==nil then variants[fullname]={} end
			variants[fullname][spec]=true
		end
	end
	local result={}
	for fullname, specset in pairs(variants) do
		local speclist={}
		for spec, _ in pairs(specset) do table.insert(speclist, spec) end
		table.sort(speclist)
		table.insert(result, ('\\cs_generate_variant:Nn \\%s {%s}\n'):format(fullname, table.concat(speclist, ",")))
	end
	table.sort(result)
	return table.concat(result)
end

end
