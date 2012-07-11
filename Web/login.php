<?php
	if(isset($_POST['username']) && isset($_POST['password'])) {
		setcookie('username',$_POST['username'],-1);
		setcookie('token',hash('sha256',$_POST['password']),-1);
		die(header("Location: /"));
	} else {
?>
<form method="POST">
	<p>Username: <input type="text" name="username" /></p>
	<p>Password: <input type="password" name="password" /></p>
	<p><input type="submit" value="login" /></p>
</form>
<?php } ?>
