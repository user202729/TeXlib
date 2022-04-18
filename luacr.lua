-- global variable
if luacr then
	error("luacr global variable is already defined!")
end

luacr={}

do

local function check_within_luacr_coroutine()
	if luacr.coroutine~=coroutine.running() then
		error("luacr function used outside luacr.exec()")
	end
end

-- join several tables, overwrite the first one!
local function join_table(...)
	local result={}
	for i, table in ipairs({...}) do
		for i, v in ipairs(table) do
			result[#result+1]=v
		end
	end
	return result
end

-- main execution function. To use other functions, they must be used within luacr.exec(function() ... end)
-- same way how coroutine.* functions can only be used within coroutine.start()
function luacr.exec(f)
	if luacr.coroutine~=nil then
		check_within_luacr_coroutine()
		return f()
	end

	luacr.coroutine=coroutine.create(function()
		f()
		check_within_luacr_coroutine()
		luacr.coroutine=nil
	end)
	coroutine.resume(luacr.coroutine)
end

local bgroupT=token.create(string.byte "{", 1)
local egroupT=token.create(string.byte "}", 2)


-- syntactic sugar to create new token object
local T={}
luacr.T=T  -- also expose it if people want to use
setmetatable(T, {
	__index=function(T, csname)
		return token.create(csname)
	end
})


function luacr.flush()
	check_within_luacr_coroutine()
	token.put_next(T._luacr_continue)
	coroutine.yield()
end

-- execute some tokens. E.g. \let\a\undefined. tokens can be string or table of tokens.
function luacr.tex_exec(tokens)
	tex.sprint(tokens)
	tex.sprint(T.relax)
	luacr.flush()
end

-- expand once the following tokens in the input stream
function luacr.expandafter()
	check_within_luacr_coroutine()
	token.put_next({T.expandafter, T._luacr_continue})
	coroutine.yield()
end

-- o-expand the given token list.
function luacr.exp_o(tokens)
	tex.sprint({T["exp_args:No"], T._luacr_storetl, bgroupT})
		tex.sprint(tokens)  -- allow tokens to be either string or list of tokens
		tex.sprint(egroupT)
	luacr.flush()
	return luacr._stored_tl
end

-- x-expand the given token list.
function luacr.exp_x(tokens)
	tex.sprint({T["exp_args:Nx"], T._luacr_storetl, bgroupT})
		tex.sprint(tokens)  -- allow tokens to be either string or list of tokens
		tex.sprint(egroupT)
	luacr.flush()
	return luacr._stored_tl
end

-- similar to token.create, but is safe, works even if the cs is never seen.
function luacr.safe_create(csname)
	tex.sprint({T.expandafter, T._luacr_continue, T.ifcsname})
		tex.sprint(-2, csname)  -- -2: print as detokenized
		tex.sprint({T.endcsname, T.fi, T.n})
	-- in summary   print: \expandafter \_luacr_continue \ifcsname <...> \endcsname \fi \n \_luacr_continue
	-- if true  expand to: \_luacr_continue \fi \n \_luacr_continue
	-- if false expand to: \_luacr_continue \n \_luacr_continue
	luacr.flush()

	-- the first _luacr_continue
	if token.get_next().csname == "fi" then
		token.get_next() -- next is \n
		-- okay it's not impossible, easy case
	else
		-- it's impossible
		-- print \expandafter \let \csname <...> \endcsname \undefined , already have a following \_luacr_continue
		-- with an immediateassignment just in case this is executed in expansion-only context...
		-- still doesn't work in case of o-expansion however.
		tex.sprint({T.expandafter, T.immediateassignment, T.expandafter, T.let, T.csname})
			tex.sprint(-2, csname)
			tex.sprint({T.endcsname, T.undefined})
		-- now it's possible, but still undefined
	end

	coroutine.yield()  -- run to the second _luacr_continue
	return token.create(csname)
end

-- similar to get_next(), but is safe, work even if the next token is never seen
function luacr.safe_get_next()
	check_within_luacr_coroutine()
	token.put_next({
		T.immediateassignment, T.futurelet, T._luacr_unused, T._luacr_continue
	})
	coroutine.yield()
	return token.get_next()
end

function luacr.to_str(tokens)
	check_within_luacr_coroutine()
	tex.sprint({T["exp_args:No"], T._luacr_storetl, bgroupT, T.detokenize, bgroupT})
	tex.sprint(tokens)
	tex.sprint({egroupT, egroupT})
	token.put_next(T._luacr_continue)
	coroutine.yield()
	return luacr._stored_tl
end

end
