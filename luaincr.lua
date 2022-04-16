do
	local posix=require "posix"

	local function readfile(source)  -- return string
		local infile=io.open(source, "rb")
		local content=infile:read("*all")
		infile:close()
		return content
	end

	local function copyfile(source, target)
		local infile=io.open(source, "rb")
		--os.execute("ls")
		
		os.execute(
			("if [ -f 'source' ]; then cp -l 'source' 'target'; else rm 'target'; fi")
			:gsub('source', source)
			:gsub('target', target)
			)

		--os.execute(
		--	--("if [ -f 'source' ]; then cp 'source' 'target'; else rm 'target'; fi")
		--	("if [ -f 'source' ]; then rm 'target'; cp 'source' 'target'; else rm 'target'; fi")
		--	:gsub('source', source)
		--	:gsub('target', target)
		--	)


		--os.remove(target) -- seems to work more reliably this way (new inode, I think?)
		--if infile==nil then
		--	--print(":: "..source.." ∄ → kill "..target)
		--else
		--	--print(":: "..source.." → "..target)
		--	local outfile=io.open(target, "wb")
		--	outfile:write(infile:read("*all"))
		--	infile:close()
		--	outfile:close()
		--end
	end

	local extensions={".pdf", ".aux", ".log", ".fls", ".synctex(busy)", ".synctex", ".synctex.gz"}
	local T=luacr.T

	luaincr={
		server=function() luacr.exec(function()

			--close aux file. Will reopen later...
			luacr.tex_exec{
				T.immediate, T.closeout, T["@auxout"]
			}

			--first backup the partial PDF content
			for _,extension in pairs(extensions) do
				copyfile(tex.jobname..extension, "backup-"..tex.jobname..extension)
			end
			local aux_content=readfile(tex.jobname..".aux")
			if aux_content:sub(-1) == "\n" then
				aux_content=aux_content:sub(1, -2)
			end

			--local num_iter = 0 -- DEBUG
			while true do
				local pid = posix.fork()
				if pid == 0 then
					-- is child, continue running

					-- (attempt to restore files)
					--for _,extension in pairs(extensions) do
					--	copyfile("backup-"..tex.jobname..extension, tex.jobname..extension)
					--end

					tex.sprint{
						T.immediate, T.openout, T["@auxout"], "=" .. tex.jobname .. ".aux",
						T.immediate, T.write, T["@auxout"], "{"
					}
					tex.sprint(-2, aux_content)  -- -2: detokenized
					tex.sprint "}"
					luacr.flush()

					-- ("reload" the file)
					--print(token.get_macro("currfilepath"))
					local infile=io.open(token.get_macro("currfilepath"), "r")
					for i=1,tex.inputlineno do
						infile:read()
					end
					while true do
						local data=infile:read()
						if data==nil then
							break
						end
						--print(data) --DEBUG
						tex.print(data)
					end
					infile:close()
					break
				else
					-- is parent
					posix.wait(pid) 
					print("======== Press enter to recompile ========")
					io.read() -- DEBUG
					-- **critical**: restore the partial PDF content
					for _,extension in pairs(extensions) do
						copyfile("backup-"..tex.jobname..extension, tex.jobname..extension)
					end
				end

				---- DEBUG
				--num_iter=num_iter+1
				--if num_iter>=2 then break end
			end

			end)
		end
	}
end

--[[

rm z; mkfifo z; when-changed -1 ../a.tex 'sleep 0.1s; echo >z' & tail -f z | lualatez ../a.tex

]]
