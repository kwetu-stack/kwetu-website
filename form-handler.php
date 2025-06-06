<?php
$name=$_POST['name'];
$visitor-email=$_POST['email'];
$subject=$_POST['subject'];
$message=$_POST['message'];

$email-from='info@joiafra.net';

$email-subject='New Form Submission';

$email-body="User Name:$name.\n".
             "User Email: $visitor-email.\n".
             "Subject: $subject.\n". 
             "User Message: $visitor-email.\n";

$to='joykairra@gmail.com';

$headers="From: $email-from\r\n";

$headers.="Reply-To: $visitor-email\r\n"


mail($to,$email-subject,$email-body,$headers);

header("Location:contact.html");
?>
