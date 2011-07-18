/**
 * This class is the client-side representation for the permutation features of 
 * Jasy and supports features like auto-selecting builds based on specific feature sets.
 */
(function(global, undef)
{
	// The build system is replacing this call via the loader permutation
	var fields = Permutation.getValue("Permutation.fields");
	
	// Stores all selected fields in a simple map
	var selected = {};
	
	var checksum = fields ? (function()
	{
		// Process entries
		var key = [];
		for (var i=0, l=fields.length; i<l; i++) 
		{
			var entry = fields[i];
			var name = entry[0];
			var allowed = entry[1];
			
			var test = entry[2];
			if (test)
			{
				var value = "VALUE" in test ? test.VALUE : test.get(name);
				
				// Fallback to first value if test results in unsupported value
				if (value == null || allowed.indexOf(value) == -1) {
					value = allowed[0];
				}
			}
			else
			{
				// In cases with no test, we don't have an array of fields but just a value
				value = allowed;
			}

			selected[name] = value;
			key.push(name + ":" + value);
		}
		
		var adler32 = (function(data)
		{
			var MOD_ADLER = 65521;
			var a=1, b=0;

			// Process each byte of the data in order
			for (var index=0, len=data.length; index<len; ++index)
			{
				a = (a + data.charCodeAt(index)) % MOD_ADLER;
				b = (b + a) % MOD_ADLER;
			}

			return (b << 16) | a;
		})(key.join(";"));
		
		var prefix = adler32 < 0 ? "a" : "b";
		var checksum = prefix + (adler32 < 0 ? -adler32 : adler32).toString(16);
		
		return checksum;
	})() : "";
	
	Module("Permutation",
	{
		/** {Map} Currently selected fields from Permutation data */
		selected : selected,

		/** {Number} Holds the checksum for the current permutation which is auto detected by features or by compiled-in data */
		CHECKSUM : checksum,
		
		isEnabled : function(name) {
			return selected[name] == true;
		},
		
		isSet : function(name, value) {
			return selected[name] == value;
		},
		
		getValue : function(name) {
			return selected[name];
		},

		loadScripts : function(uris)
		{
			var patched = [];
			for (var i=0, l=uris.length; i<l; i++) {
				patched[i] = this.patchFilename(uris[i]);
			}

			return jasy.Loader.loadScripts(patched);
		},

		patchFilename : function(fileName) 
		{
			var pos = fileName.lastIndexOf(".");
			var checksum = "-" + this.CHECKSUM;

			if (pos == -1)
			{
				return fileName + checksum;
			}
			else
			{
				var fileExt = fileName.substring(pos+1);
				return fileName.substring(0, pos) + checksum + "." + fileExt;
			}
		}
	});
})(this);

