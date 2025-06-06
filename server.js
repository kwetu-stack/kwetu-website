// server.js
const express = require('express');
const bodyParser = require('body-parser');
const path = require('path');

const app = express();
const PORT = 3000;

app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static(__dirname));

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.post('/login', (req, res) => {
  const { username, password } = req.body;
  console.log('Login:', username, password);
  res.send('Login received! (Check your server console)');
});

app.post('/signup', (req, res) => {
  const { username, email, password, confirm_password } = req.body;
  console.log('Signup:', username, email, password, confirm_password);
  res.send('Signup received! (Check your server console)');
});

app.post('/send-message', (req, res) => {
  const { name, email, subject, message } = req.body;
  console.log('Contact message:', name, email, subject, message);
  res.send('Message received! (Check your server console)');
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});

