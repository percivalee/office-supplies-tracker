[Setup]
AppId={{BE0C5031-3EE9-450D-9F17-84526F27F5B5}
AppName=办公用品采购系统
AppVersion=1.2.2
DefaultDirName={autopf}\OfficeSuppliesTracker
DefaultGroupName=办公用品采购系统
OutputDir=dist
OutputBaseFilename=办公用品采购系统-安装包
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务"; Flags: unchecked

[Files]
Source: "dist\办公用品采购系统-文件夹版\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\办公用品采购系统"; Filename: "{app}\办公用品采购系统-文件夹版.exe"
Name: "{autodesktop}\办公用品采购系统"; Filename: "{app}\办公用品采购系统-文件夹版.exe"; Tasks: desktopicon
