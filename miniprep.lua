return function(str, mode)
	-- str is either empty or ends with "\n"
	-- lines are separated by "\n"

	print()
	print()
	print()
	print()

	local L=require "luamacrohelper"
	local T=L.T
	local E3=L.E3

	local function notdoc(fn)
		if mode=="doc" then return function() return "" end end
		return fn
	end

	local function precattl(code)
		assert(L.is_tl(code))
		L.runlocal(L.shorthand_tl {
			T["precattl_set:Nn"], T._miniprep_tokens, code
		})
		return L.get_macro(T._miniprep_tokens)
	end

	local function tlserialize(code)
		local result=tlserialize_unchecked(code)
		-- TODO very, very bad hack (see also the part of serializing characters >=0x80 in tlserialize)
		--local comparison=tldeserialize(result)
		--assert(#code==#comparison)
		--for i=1, #code do
		--	if not (type(code[i].tok)=="string" and code[i].tok:gmatch "^faketoken")
		--		and code[i].tok~=comparison[i].tok
		--	then
		--		error("token "..L.detokenize_str({comparison[i]}).." cannot be serialized")
		--	end
		--end
		return result.."\n"
	end

	local transform_functions={
		verbatim=notdoc(function(code) return code end),
		replace=notdoc(function(code, arg)
			local result, num_match=code:gsub("__", arg)
			if num_match==0 then
				error("[replace: "..arg.."] cannot find any replacement!")
			end
			return result
		end),

		-- execute something (Lua code) in the compiler...
		compiler_execute=notdoc(function(code) return load(code)() or "" end),

		ignore=function() return "" end,

		expl_tokenize=notdoc(function(code) return L.expl_tokenize(code) end),
		precattl_raw=notdoc(precattl),

		precattl=notdoc(function(code)
			assert(type(code)=="string")
			return tlserialize(precattl(L.expl_tokenize(code)))
		end),

		tlserialize=notdoc(function(code)
			assert(L.is_tl(code))
			return tlserialize(code)
		end),

		quote_to_tilde=notdoc(function(code)
			local index=0
			local result={}
			for part in code:gmatch '[^"]*' do
				if index%2==0 then
					if #part==0 then
						result[#result+1]='"'  -- two consecutive " in a string results in a single "
					else
						result[#result+1]=part
					end
				else
					result[#result+1]=part:gsub(" ", "~")
				end
				index=index+1
			end
			return table.concat(result)
		end),

		genvar=notdoc(function(code)
			local genvar=require "genvar"
			return genvar(code)..code
		end),

		debug=notdoc(function(code, arg)
			if arg=="on" then
				return code:gsub('debug%(%(', ''):gsub('debug%)%)', '')
			elseif arg=="off" then
				return code:gsub('debug%(%(.-%)%)', '')
			else
				print("invalid: arg="..arg..", should be 'on' or 'off'")
				assert(false)
			end
		end),

		precat=notdoc(function(code)
			local precat=require "precat"
			return tlserialize(precat(code))
		end),

		imperative=notdoc(function(code, arg, lastlinenumber)
			assert(type(code)=="string")
			code=code:gsub("\n", "\r")  -- annoyingly addlinemarker takes ^^M instead of ^^J
			L.runpeek(L.shorthand_tl {
				T["addlinemarker:nnn"],
					-- tokens to be put after
					{
						T.endlocalcontrol,
					},
					-- the body
					L.str_to_strtl(code),
					L.str_to_strtl(tostring(lastlinenumber)),
			})
			local code_linemarked=L.scan_toks()

			-------- then

			local result=(compile_outer(
					precattl(code_linemarked)
			)) -- parenthesis to get first return value only.

			-------- prepend the compiled helper functions

			optimize_pending_definitions()
			if imperative_debug then debug_rdef() end
			result=cat(get_execute_pending_definitions_tl(pending_definitions), result)
			pending_definitions={}

			if imperative_debug then
				prettyprint("going to execute", result)
			end

			-------- serialize and return
			return tlserialize(result)
		end),

		doc=function(code)
			if mode=="doc" then return code end
			return ""
		end
	}

	local last_rule=nil
	local result={}
	local lastlinenumber=0
	for code, rule in (str.."\n========\n"):gmatch "(.-\n)========(.-)\n" do
		local _, num_lines=code:gsub("\n", "")
		lastlinenumber=lastlinenumber+num_lines+1
		if last_rule~=nil then
			for transform in (last_rule..","):gmatch " *(.-) *," do  -- note that transform will not end with a space
				local transform_function_name, arg=transform:match "(.-): *(.*)"  -- remove any leading space in arg
				if transform_function_name==nil then
					transform_function_name=transform
				end

				local transform_function=transform_functions[transform_function_name]
				if transform_function==nil then
					error("cannot find function: "..transform_function_name)
				end

				print(":: applying transformer "..transform_function_name)
				code=transform_function(code, arg, lastlinenumber)
			end

			assert(type(code)=="string")
			result[#result+1]=code
		end
		last_rule=rule
	end
	assert(last_rule=="")


	-- return by print to TeX
	tex.sprint(-2, table.concat(result))
end
