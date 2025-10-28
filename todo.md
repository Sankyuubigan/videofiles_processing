

# надо сделать
1. по дефолту надо сделать чтобы стояло изначально пресет "slow".
4. всё что щас в окне программы это должна быть первая основная вкладка. логи выносим в отдельную вкладку вторую и назовем её логи. причем щас логи все идут в консоль а не в наше окно гуи. надо чтобы все абсолютно логи шли в наше окно гуи во вкладку логи туда.
5. нужно добавить функцию удаления из очереди конкретного видео через гуи через кнопку.

перевод
1. нам нужно при склейке переведенного видео добавлять вторую аудиодорожку оригинальную без перевода. а первая будет дефолтная переведенная остаётся.
2. нужно добавить опцию выбрать не 1 файл, а папку с видео, и он будет все видео в этой папке переводить
3. пусть переведенное видео сохраняется в тот же путь где лежит оригинал, то есть где выбирали файл путь. если выбрана папка видео то тот же путь просто папка будет с другим названием.






# проверить

когда я запускаю свою программу то она работает, но в логах ошибка и какие то нули. нахуй нужны эти нули и о чем ошибка?
нужны при старте программы логи, на чем выполняться будет сжатие. на видеокарте или процессоре. пусть выводит в консоль какая именно гпу, информацию.
сейчас общий процент всех видео в списке глючит и неверно показывает. в процентах общий должен процент писать по всем видео в очереди. а он начинает работать нормально только когда последнее видео в списке начинает сжиматься. а до этого он работает плохо некорректно показывает процент.
когда я нажал на отмену сжатия, то кнопка отмены исчезла но нихуя процесс не остановился. я никак не могу закрыть программу потому что он всё ещё сжимает.

1. нам надо сбилдить екзешник через пайинсталлер чтобы не было системных зависимостей. у нас в проекте лежит файл ffmpeg.exe поэтому надо его использовать и нам нужен экзешник. сделай файл билд на питоне и он будет билдить нам экзешник.
2. нужно добавить кнопку где я смогу выбрать путь сохранения видеофайлов. это необязательно, опционально. по дефолту пусть выбирается всегда тот же путь где и видеофайлы лежали оригиналы. но если указываю путь сохранения то все видео из очереди пусть сохраняются в эту папку.
3. файл майн слишком большой стал. давай разделим код в другой файл чтобы не был таким огромным. вынесем часть логики. и файл видеопроцессор тоже огромный.


он написал мне щас что файл будет примерный размер 39 мб, но файл вышел после сжатия 30 мб. оригинал весил 60 мб вебм, можно ли как то улучшить предварительный размер примерный информацию чтобы расхождения такого не было ? он врёт и неверный пишет щас предварительный размер. если я выбираю файл мп4 оригинал 180 мб, то пишет примерный размер 115 мб, а результат получается 32 мб. если выбираю видео с исправным VFR, то вебм файл оригинал который весит 80 мб, пишет что примерный размер у него будет 50 мб, а результат получается 92 мб, то есть вообще сжатие не работает почему то.


# в разработке
не все домены видит на данный момент во вкладке домены, когда идёт поиск на сайте доменов. он лишь часть выдаёт. в то время как в хроме через ф12 девтулс там в консоли выдает больше намного доменов, мне приходится вручную оттуда брать чтобы работали сайты. надо усовершенствовать поиск доменов на сайте наш чтобы выдавал полный список доменов. вот что выдаёт девтулс консоль:

GET https://static.cloudflareinsights.com/beacon.min.js/vcd15cbe7772f49c399c6a5babf22c1241717689176015 net::ERR_BLOCKED_BY_CLIENT
VM141:1 
        
        
       GET https://bat.bing.com/bat.js net::ERR_BLOCKED_BY_CLIENT
(анонимная) @ VM141:1
(анонимная) @ VM141:1
p @ 7485-6d79d9b0b3933bc6.js:1
(анонимная) @ 7485-6d79d9b0b3933bc6.js:1
aW @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oe @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
or @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ol @ 1dd3208c-6fbbf9e01dcb1c66.js:1
id @ 1dd3208c-6fbbf9e01dcb1c66.js:1
o @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755721440_958082.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250812/screenshots/screenshot_1754988702_804907.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755784276_323663.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250826/screenshots/screenshot_1756183106_350488.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250816/screenshots/screenshot_1755356788_887971.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250812/screenshots/screenshot_1754969193_570967.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250824/screenshots/screenshot_1756034536_158209.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
1dd3208c-6fbbf9e01dcb1c66.js:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755874671_785111.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET 200 (OK)
preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
t.preload @ 1dd3208c-6fbbf9e01dcb1c66.js:1
v @ 294-de060792e1023165.js:1
rE @ 1dd3208c-6fbbf9e01dcb1c66.js:1
iZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
ia @ 1dd3208c-6fbbf9e01dcb1c66.js:1
(анонимная) @ 1dd3208c-6fbbf9e01dcb1c66.js:1
il @ 1dd3208c-6fbbf9e01dcb1c66.js:1
oZ @ 1dd3208c-6fbbf9e01dcb1c66.js:1
M @ 1528-77d68c59cd131ec5.js:1
agent-cdn.minimax.io/screenshot/20250824/screenshots/screenshot_1756043686_743871.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250824/screenshots/screenshot_1756043686_743871.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250812/screenshots/screenshot_1754989797_139238.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250812/screenshots/screenshot_1754989797_139238.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755766533_311107.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755766533_311107.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250820/screenshots/screenshot_1755684531_434655.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250820/screenshots/screenshot_1755684531_434655.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250826/screenshots/screenshot_1756175877_416409.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250826/screenshots/screenshot_1756175877_416409.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755842527_143552.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755842527_143552.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755839522_624324.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755839522_624324.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250825/screenshots/screenshot_1756123724_575274.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250825/screenshots/screenshot_1756123724_575274.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755839032_905404.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250822/screenshots/screenshot_1755839032_905404.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250824/screenshots/screenshot_1756021464_752047.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250824/screenshots/screenshot_1756021464_752047.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755770877_476105.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250821/screenshots/screenshot_1755770877_476105.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET
agent-cdn.minimax.io/screenshot/20250728/screenshots/screenshot_1753690392_677684.png?x-oss-process=image/resize,p_25:1 
        
        
       GET https://agent-cdn.minimax.io/screenshot/20250728/screenshots/screenshot_1753690392_677684.png?x-oss-process=image/resize,p_25 net::ERR_CONNECTION_RESET 200 (OK)