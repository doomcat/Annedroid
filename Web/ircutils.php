<?php
	function irc_get_hostname() {
		if(isset($_SERVER['HTTP_HOST'])) {
			$pos = stripos($_SERVER['HTTP_HOST'], '.irc.slashingedge.co.uk');
			if($pos !== false) {
				return substr($_SERVER['HTTP_HOST'],0,$pos);
			}
		}
		return 'irc.aberwiki.org';
	}
?>
