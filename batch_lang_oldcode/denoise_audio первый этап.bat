
set /p "file_name=drag and swap file: "
rem ffmpeg -i %file_name% -filter_complex "asplit [a1][a2];[a1] arnndn=m='rnn_models/beguiling-drafter-2018-08-30/bd.rnnn' [o1];[a2] arnndn=m='rnn_models/leavened-quisling-2018-08-31/lq.rnnn' [o2]" -map '[o1]' -codec:a pcm_s24le %file_name:.=_test1.% -map '[o2]' -codec:a pcm_s24le %file_name:.=_test2.%

rem ffmpeg -i %file_name% -af "arnndn=m='rnnoise-models/somnolent-hogwash-2018-09-01/sh.rnnn'" %file_name:.=_denoised.%


ffmpeg -i %file_name% -af "arnndn=m='rnnoise-models/beguiling-drafter-2018-08-30/bd.rnnn'" %file_name:.=_deno1.%

pause




rem 2.
rem afftdn
rem anlmdn
rem arnndn
rem ladspa (noise-supressor)
rem lv2 (speech denoiser)

