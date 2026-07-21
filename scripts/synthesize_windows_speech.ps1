param(
    [Parameter(Mandatory = $true)][string]$TextFile,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$Voice = "Microsoft Huihui Desktop"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $installed = $synth.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Name -eq $Voice }
    if (-not $installed) {
        throw "未找到本地语音：$Voice"
    }

    $textPath = [IO.Path]::GetFullPath($TextFile)
    $outputPath = [IO.Path]::GetFullPath($Output)
    $text = [IO.File]::ReadAllText($textPath, [Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "口播文本不能为空"
    }

    $synth.SelectVoice($Voice)
    $synth.SetOutputToWaveFile($outputPath)
    $synth.Speak($text)
}
finally {
    $synth.Dispose()
}
