<?php
	if(!isset($_COOKIE['username']) || !isset($_COOKIE['token'])) {
		die(header("Location: /login.php"));
	}
	require_once("ircutils.php");
?>
<html>
	<head>
		<title>Annedroid - #42 Feed</title>
		<script type="text/javascript" src="/date.format.js"></script>
		<script type="text/javascript" src="http://code.jquery.com/jquery-1.7.2.min.js"></script>
		<script type="text/javascript">
			var server = '<?php echo irc_get_hostname(); ?>'
			var nick = 'TestUser'
			var last_checked = 0;
			var unread = 0;
			var focused = true;
			var username = '<?php echo $_COOKIE['username']; ?>';
			var ctime = '';
			var token = '<?php echo $_COOKIE['token']; ?>';

			function escape(s) {
				return jQuery('<div/>').text(s).html();
			}

			function urlify(text) {
			    var urlRegex = /(https?:\/\/[^\s]+)/g;
			    var imgRegex = /\.(gif|png|jpg)/g;
				    return text.replace(urlRegex, function(url) {
					if(url.search(imgRegex) != -1) {
						return '<a href="'+url+'" target="_new"><img src="'+url+'" /></a>';
					}
			        return '<a href="' + url + '" target="_new">' + url + '</a>';
			    })
			}

			function getChat() {

				pdata = {"user": username, "ctime": ctime,
					"token": token, "limit": 50,
					"server": server, "channel": window.location.hash, "last_checked": last_checked, "wait": "true"};
				$.post(
					'/api/channel/new',
					pdata,
					function(data, status, xhr) { try{
						d = data;
						console.log(d);
						for(var m in d['messages']) {
							nick_class = '';
							nick = d.messages[m].nick;
							i = nick.indexOf('!');
							if(i != -1) {
								nick = d.messages[m].nick.substring(0,i);
							}
							nick = escape(nick);
							message = escape(d.messages[m].message);
							message = urlify(message);
							msg = message;
							if(d.messages[m].nick.indexOf('!self') != -1) {
								nick_class += ' self';
							}
							if(d.messages[m].highlight == true) {
								nick_class += " highlight";
							}
							if(d.messages[m].event) {
								nick_class += ' event';
								message = '';
							}
							if(d.messages[m].event == "ACTION") {
								nick += ' '+msg;
							} else if(d.messages[m].event == "JOINED") {
								nick += ' has joined the channel';
							} else if(d.messages[m].event == "LEFT" || d.messages[m].event == "QUIT") {
								nick += ' has left the channel';
							} else if(d.messages[m].event == "OTHER_KICKED") {
								nick += ' has been kicked by '+msg;
							} else if(d.messages[m].event == "SELF_KICKED") {
								nick += ' has kicked you: '+msg;
							} else if(d.messages[m].event == "NEW_TOPIC") {
								nick = '<u>Topic</u>: '+msg;
							}
                                                        time = new Date(parseFloat(d.messages[m].timestamp)*1000);
                                                        timeStr = "Sent at "+time.format("HH:MM");
							$("#container").append('<p class="'+nick_class+'"><span class="nick" title="'+timeStr+'">'+nick+
							'</span><span class="message">'+message+'</span></p>');
							last_checked = d.messages[m].timestamp;
						}
						scrollY = $(window).scrollTop()+$(window).height();
						heightY = ($("#container").height()-$("#chatForm").height())-30;
						if(!focused || scrollY < heightY) {
							unread++;
							document.title = '('+unread+') '+window.location.hash;
						}
						if(scrollY >= heightY) {
							$('html, body').animate({
								scrollTop: $("#anchor").offset().top
							}, 1000);
						}
						$("#container p:last").hide().fadeIn();
						getChat();
						} catch(err) { setTimeout("getChat()", 3000); }
					},
					'json'
				).error(function(){ setTimeout("getChat()", 3000); });
			}

			$(document).ready(function() {

				$("#chatForm").submit(function() {
					message = $("input[name=message]").val();
					pdata = {"user": username, "ctime": ctime,
						"token": token,
						"server": server, "channel": window.location.hash, "message": message};
					$.post('/api/server/message', pdata, null, 'json');
					$("input[name=message]").val('');
					return false;
				});
				window.onfocus = function() {
					focused = true;
					unread = 0;
					document.title = window.location.hash;
				}
				window.onblur = function() {
					focused = false;
				}
				getChat();
			});

		</script>
		<style>
			@import url(http://fonts.googleapis.com/css?family=Droid+Sans:400,700);
			body{
				font-family: "Droid Sans", "Trebuchet MS", sans-serif;
				font-size: 12pt;
				background-color: #000;
				color: #eee;
				padding: 0px;
				margin: 0px;
			}

			a, a:visited{
				color: inherit;
			}
			img{
				max-width: 96px;
				max-height: 96px;
			}
			img:active{
				max-width: 70%;
				max-height: 70%;
			}
			.nick{
				font-weight: bold;
				background-color: #333;
				color: #fff;
				font-size: 80%;
				padding: 1.5em;
				margin-right: 1em;
				margin-left: -0.5em;
				line-height: 1.5em;
				text-shadow: #000 0px 0px 10px;

				-webkit-border-bottom-right-radius: 6px;
				-webkit-border-bottom-left-radius: 6px;
				-moz-border-radius-bottomright: 6px;
				-moz-border-radius-bottomleft: 6px;
				border-bottom-right-radius: 6px;
				border-bottom-left-radius: 6px;
				
				/* IE10 Consumer Preview */ 
				background-image: -ms-linear-gradient(top, #333333 0%, #666666 100%);

				/* Mozilla Firefox */ 
				background-image: -moz-linear-gradient(top, #333333 0%, #666666 100%);

				/* Opera */ 
				background-image: -o-linear-gradient(top, #333333 0%, #666666 100%);

				/* Webkit (Safari/Chrome 10) */ 
				background-image: -webkit-gradient(linear, left top, left bottom, color-stop(0, #333333), color-stop(1, #666666));

				/* Webkit (Chrome 11+) */ 
				background-image: -webkit-linear-gradient(top, #333333 0%, #666666 100%);

				/* W3C Markup, IE10 Release Preview */ 
				background-image: linear-gradient(to bottom, #333333 0%, #666666 100%);
			}
			.nick *{
				vertical-align: bottom;
			}
			p{
				display: block;
				margin: 0px 0px;
				border-top: 1px solid #333;
				padding: 1em 1.5em;
				line-height: 2em;
background-image: linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,0) 100%);
background-image: -o-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,0) 100%);
background-image: -moz-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,0) 100%);
background-image: -webkit-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,0) 100%);
background-image: -ms-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,0) 100%);

background-image: -webkit-gradient(
	linear,
	left bottom,
	left top,
	color-stop(0.0, rgb(17,17,17)),
	color-stop(1.0, rgb(0,0,0))
);
			}
			p *{
				vertical-align: top;
			}
			.event{
				color: #f90;
				border: none;
				background-image: none;
			}
			.event .nick:before{
				font-size: 120%;
				content: '> ';
			}
			.event .nick{
				margin: 0px;	
				display: block;
				color: #ff0;
				background-image: linear-gradient(bottom, rgb(136,0,0) 0%, rgb(85,0,0) 100%);
				background-image: -o-linear-gradient(bottom, rgb(136,0,0) 0%, rgb(85,0,0) 100%);
				background-image: -moz-linear-gradient(bottom, rgb(136,0,0) 0%, rgb(85,0,0) 100%);
				background-image: -webkit-linear-gradient(bottom, rgb(136,0,0) 0%, rgb(85,0,0) 100%);
				background-image: -ms-linear-gradient(bottom, rgb(136,0,0) 0%, rgb(85,0,0) 100%);
				background-image: -webkit-gradient(
					linear,
					left bottom,
					left top,
					color-stop(0.0, rgb(136,0,0)),
					color-stop(1.0, rgb(85,0,0))
				);
				border-radius: 6px;
				-webkit-border-radius: 6px;
				-moz-border-radius: 6px;
				line-height: .2em;
			}

			.self{
				text-align: right;
				border-color: rgb(0,85,0);
background-image: linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,34,0) 100%);
background-image: -o-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,34,0) 100%);
background-image: -moz-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,34,0) 100%);
background-image: -webkit-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,34,0) 100%);
background-image: -ms-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,34,0) 100%);

background-image: -webkit-gradient(
	linear,
	left bottom,
	left top,
	color-stop(0, rgb(17,17,17)),
	color-stop(1, rgb(0,34,0))
);
			}
			.self .nick{
				color: #ff0;
				background-image: linear-gradient(bottom, rgb(0,136,0) 0%, rgb(0,85,0) 100%);
				background-image: -o-linear-gradient(bottom, rgb(0,136,0) 0%, rgb(0,85,0) 100%);
				background-image: -moz-linear-gradient(bottom, rgb(0,136,0) 0%, rgb(0,85,0) 100%);
				background-image: -webkit-linear-gradient(bottom, rgb(0,136,0) 0%, rgb(0,85,0) 100%);
				background-image: -ms-linear-gradient(bottom, rgb(0,136,0) 0%, rgb(0,85,0) 100%);
				background-image: -webkit-gradient(
					linear,
					left bottom,
					left top,
					color-stop(0.0, rgb(0,136,0)),
					color-stop(1.0, rgb(0,85,0))
				);
				float: right;
				margin-top: -1.3em;
				margin-right: -0.5em;
				margin-left: 1em;

			}

			.self.event{
				background: none;
				text-align: right;
			}

			.self.event .nick {
				margin: 0.5em;
				float: none;
			}

			.highlight{
				font-weight: bold;
				color: #bdf;
				border-color: rgb(0,34,85);
background-image: linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,34) 100%);
background-image: -o-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,34) 100%);
background-image: -moz-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,34) 100%);
background-image: -webkit-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,34) 100%);
background-image: -ms-linear-gradient(bottom, rgb(17,17,17) 0%, rgb(0,0,34) 100%);

background-image: -webkit-gradient(
	linear,
	left bottom,
	left top,
	color-stop(0, rgb(17,17,17)),
	color-stop(1, rgb(0,0,34))
);
}

			.highlight .nick{
				color: #09f;
background-image: linear-gradient(bottom, rgb(0,84,110) 0%, rgb(0,34,85) 100%);
background-image: -o-linear-gradient(bottom, rgb(0,84,110) 0%, rgb(0,34,85) 100%);
background-image: -moz-linear-gradient(bottom, rgb(0,84,110) 0%, rgb(0,34,85) 100%);
background-image: -webkit-linear-gradient(bottom, rgb(0,84,110) 0%, rgb(0,34,85) 100%);
background-image: -ms-linear-gradient(bottom, rgb(0,84,110) 0%, rgb(0,34,85) 100%);

background-image: -webkit-gradient(
	linear,
	left bottom,
	left top,
	color-stop(0, rgb(0,84,110)),
	color-stop(1, rgb(0,34,85))
);

			}

			#anchor{
				margin-top: 4em;
			}
			#chatForm {
				position: fixed;
				left: 0px;
				right: 0px;
				bottom: 0px;
				border: none;
				border-top: 2px solid #333;
				padding: 0px;
				margin: 0px;
			}
			#chatForm input[type=text] {
				display: block;
				width: 100%;
				background-color: #000;
				padding: .2em;
				margin: 0px;
				font-size: 120%;
				color: #ddd;
				border: none;
			}
			#chatForm input[type=submit] {
				display: none;
			}
		</style>
		<style media="screen and (max-device-width: 800px),(max-width: 800px)">
			body{
				font-size: 14pt;
				margin: 0px;
				padding: 0px;
			}
			p{
				margin: .75em 0px;
				padding: .4em .8em;
				text-wrap: unrestricted;
			}
			p.self {
				padding: .3em .8em;
			}
			.nick{
				font-size: 70%;
				font-weight: normal;
				text-wrap: unrestricted;
			}
			.event .nick{
				font-size: 100%;
			}
		</style>
		<meta name="viewport" content="width=device-width, user-scalable=no" />
	</head>
	<body><div id="container">
	<noscript><p><span class="nick">JavaScript</span> <span class="message">lol enable me u silly</span></p></noscript>
	</div><div id="anchor"></div>
	<form id="chatForm" method="post">
		<input type="text" name="message" maxlength="500" />
		<input type="submit" value="Send &gt;" />
	</form>
	</body>
</html>
