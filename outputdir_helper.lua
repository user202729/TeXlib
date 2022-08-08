return function()
	if outputdir~=nil then return end  -- something else already set this variable, given the name, it probably has the correct value...

	luatexbase.add_to_callback("open_read_file", function(file_name)
		luatexbase.remove_from_callback("open_read_file", "outputdir-temp-callback")

		local suffix="outputdir-tempfile.tex"
		assert(file_name:sub(-#suffix)==suffix, "unexpected file name:|"..file_name)

		outputdir=file_name:sub(1, -#suffix-1)  -- global
		if outputdir=="" then outputdir="./" end

		os.remove(file_name)  -- for convenience, don't clutter the file system

		return {reader=function() end}
	end, "outputdir-temp-callback")
end
