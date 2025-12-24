
set /p "file_name=drag and swap file: "

python trim_silenceV2.py %file_name% %file_name:.=_test_py_trim.% -35 1.2 0.2

pause