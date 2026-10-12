// What this build adds to the application's windows. See Rta.h.
#include "Rta.h"

#include <QAction>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QMainWindow>
#include <QMenu>
#include <QMenuBar>
#include <QPointer>
#include <QTimer>
#include <QVBoxLayout>

#include <memory>

#include "AppConfig.h"

#define PREF_RTA_CONTROLS_SHOWN "rta.ui.controlsshown"

namespace
{
	// The keyboard as ControllerConfigDialog::AutoConfigureKeyboard sets it up (see
	// play-net.patch), and the controller as RtaPad.mm reads it. Keep the three in step.
	QString ControlsText()
	{
		QString controller = QString::fromStdString(Rta::GamePadName());
		QString text;
		text += "<h3>Controller</h3>";
		if(controller.isEmpty())
			text += "<p>No game controller is attached. Plug one in (USB) or pair it (Bluetooth) at any time - "
			        "DualSense, DualShock 4, Xbox, Switch Pro and others that macOS knows work at once, with nothing to set up: "
			        "sticks, direction pad and buttons are where they are on a PlayStation pad; Options or Menu is Start, "
			        "Create, Share or View is Select (so is pressing a Sony pad's touchpad).</p>";
		else
			text += QString("<p><b>%1</b> is attached and is the pad in port 1: sticks, direction pad and buttons are where they "
			                "are on a PlayStation pad; Options or Menu is Start, Create, Share or View is Select (so is pressing "
			                "a Sony pad's touchpad). It is listened to while this window is in front.</p>")
			            .arg(controller.toHtmlEscaped());
		text += "<h3>Keyboard</h3>"
		        "<table cellspacing='0' cellpadding='3'>"
		        "<tr><td><b>Move</b> (left stick)</td><td>W&nbsp;A&nbsp;S&nbsp;D</td><td width='24'></td><td><b>Direction pad</b> (menus)</td><td>arrow keys</td></tr>"
		        "<tr><td>&#10005; cross</td><td>K</td><td></td><td>&#9675; circle</td><td>L</td></tr>"
		        "<tr><td>&#9633; square</td><td>J</td><td></td><td>&#9651; triangle</td><td>I</td></tr>"
		        "<tr><td>L1</td><td>Q</td><td></td><td>R1</td><td>E</td></tr>"
		        "<tr><td>L2</td><td>1</td><td></td><td>R2</td><td>3</td></tr>"
		        "<tr><td>L3 (press left stick)</td><td>X</td><td></td><td>R3 (press right stick)</td><td>C</td></tr>"
		        "<tr><td>Camera (right stick)</td><td>T&nbsp;F&nbsp;G&nbsp;H</td><td></td><td>Start / Select</td><td>Return / Backspace</td></tr>"
		        "</table>"
		        "<p>The four face buttons lie on I&nbsp;J&nbsp;K&nbsp;L as they lie on the pad: I on top, J left, K below, L right.<br>"
		        "Full screen: double-click the picture; Escape leaves it.<br>"
		        "Other keys, or a controller macOS does not know: <i>Settings &rarr; Controller Manager</i>.</p>";
		return text;
	}

	QPointer<QDialog> g_controls;
	QPointer<QWidget> g_mainWindow;
}

void Rta::ShowControls(QWidget* parent)
{
	if(g_controls)
	{
		g_controls->raise();
		g_controls->activateWindow();
		return;
	}
	auto dialog = new QDialog(parent);
	dialog->setAttribute(Qt::WA_DeleteOnClose, true);
	dialog->setWindowTitle("Controls");
	auto layout = new QVBoxLayout(dialog);
	auto label = new QLabel(ControlsText(), dialog);
	label->setTextFormat(Qt::RichText);
	label->setWordWrap(true);
	label->setMinimumWidth(520);
	layout->addWidget(label);
	auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
	QObject::connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::close);
	layout->addWidget(buttons);
	// the controller's name follows what is attached while the window is open
	auto timer = new QTimer(dialog);
	QObject::connect(timer, &QTimer::timeout, label, [label]() {
		auto text = ControlsText();
		if(label->text() != text) label->setText(text);
	});
	timer->start(1000);
	g_controls = dialog;
	// not modal: the game goes on, and the keys can be tried while it is read
	dialog->show();
}

// ---- the disc image ----------------------------------------------------------------------

namespace
{
	std::function<void(const std::string&)> g_discBoot;
}

void Rta::SetDiscBoot(const std::function<void(const std::string&)>& boot)
{
	g_discBoot = boot;
}

void Rta::BootDisc(const std::string& path)
{
	if(g_discBoot && !path.empty()) g_discBoot(path);
}

std::string Rta::ChooseDisc(QWidget* parent, const std::string& given, bool askAnew)
{
	auto info = Rta::GetLaunchInfo();
	if(!info.packaged) return std::string();
	QSettings launch(QString::fromStdString(info.root + "/launch.ini"), QSettings::IniFormat);
	QString candidate = given.empty() ? QString::fromStdString(info.disc) : QString::fromStdString(given);
	if(askAnew) candidate.clear();
	if(!candidate.isEmpty() && !QFileInfo::exists(candidate))
	{
		Rta::LogLine("the disc image that was used last is not there any more: " + candidate.toStdString());
		QMessageBox::information(parent, "Disc image", QString("The disc image that was used last is not there any more:\n%1\n\nChoose it again.").arg(candidate));
		candidate.clear();
	}
	bool asked = false;
	for(;;)
	{
		if(candidate.isEmpty())
		{
			if(!asked && given.empty() && info.disc.empty() && !askAnew)
			{
				Rta::LogLine("first start: no disc image known yet; saying what is needed");
				QMessageBox::information(parent, "Disc image",
				                         "To play you need your own disc image of Champions: Return to Arms - the US release, SLUS-20973, version 2.00 "
				                         "(a file such as .iso). Nothing of the game is part of this application.\n\nChoose the file in the next window. It is remembered.");
			}
			asked = true;
			Rta::LogLine("asking for the disc image (file dialog)");
			QString start = launch.value("discdir", QDir::homePath()).toString();
			candidate = QFileDialog::getOpenFileName(parent, "Choose your disc image of Champions: Return to Arms (SLUS-20973, version 2.00)", start,
			                                         "Disc images (*.iso *.bin *.cue *.chd *.cso *.zso *.isz *.img *.mdf);;All files (*)");
			if(candidate.isEmpty())
			{
				Rta::LogLine("no disc image chosen");
				return std::string();
			}
			launch.setValue("discdir", QFileInfo(candidate).absolutePath());
		}
		std::string verdict = Rta::CheckDisc(candidate.toStdString());
		if(verdict.empty())
		{
			launch.setValue("disc", candidate);
			launch.sync();
			Rta::LogLine("disc image accepted: " + candidate.toStdString());
			return candidate.toStdString();
		}
		Rta::LogLine("disc image REFUSED: " + verdict);
		// in a test run nobody is there to pick another one
		if(Rta::IsTestRun()) return std::string();
		QMessageBox::warning(parent, "Not the right disc", QString::fromStdString(verdict) + "\n\nChoose another file.");
		candidate.clear();
	}
}

// ---- Online ------------------------------------------------------------------------------

namespace
{
	struct OnlineDialog
	{
		QDialog* dialog = nullptr;
		QLineEdit* server = nullptr;
		QSpinBox* player = nullptr;
	};

	OnlineDialog BuildOnline(QWidget* parent, const Rta::LaunchInfo& info)
	{
		OnlineDialog result;
		result.dialog = new QDialog(parent);
		QDialog& dialog = *result.dialog;
		dialog.setWindowTitle("Online");
		auto layout = new QVBoxLayout(&dialog);
		auto form = new QFormLayout();
		layout->addLayout(form);

		auto server = new QLineEdit(QString::fromStdString(info.server), &dialog);
		server->setPlaceholderText("empty: the server runs on this computer");
		server->setMinimumWidth(320);
		server->setEnabled(info.packaged);
		form->addRow("Lobby server address:", server);
		auto serverNote = new QLabel(QString("An IPv4 address or a host name; everyone in a game uses the same one.%1")
		                                 .arg(info.serverNow.empty() ? "" : QString(" This run talks to: %1.").arg(QString::fromStdString(info.serverNow).toHtmlEscaped())),
		                             &dialog);
		serverNote->setWordWrap(true);
		form->addRow("", serverNote);

		auto player = new QSpinBox(&dialog);
		player->setRange(1, 99);
		player->setValue(info.player);
		player->setEnabled(info.packaged);
		form->addRow("Player number:", player);
		auto playerNote = new QLabel("Leave it at 1. Each number has its own settings and memory card; another number is only for a second copy on the same Mac.", &dialog);
		playerNote->setWordWrap(true);
		form->addRow("", playerNote);

		QString patchText = info.patchSet.empty() ? QString("none loaded") : QString::fromStdString(info.patchSet);
		if(!info.patchSet.empty() && !info.gameChecked) patchText += "  (not applied: the game is not loaded)";
		auto patchSet = new QLabel(QString("<b>%1</b>").arg(patchText.toHtmlEscaped()), &dialog);
		patchSet->setTextInteractionFlags(Qt::TextSelectableByMouse);
		form->addRow("Patch set:", patchSet);
		auto patchNote = new QLabel("Compare the figure after \"set\" with your friends' before you start: every player in a game has to have the same.", &dialog);
		patchNote->setWordWrap(true);
		form->addRow("", patchNote);

		QString signin;
		if(!info.signinPatch.empty())
			signin = QString("found, in %1").arg(dialog.fontMetrics().elidedText(QFileInfo(QString::fromStdString(info.signinPatch)).absolutePath(), Qt::ElideMiddle, 360).toHtmlEscaped());
		else
			signin = QString("<b>not found.</b> Without it the game stops with a network error after \"Internet Game\" (the sign-in servers of 2005 are gone). "
			                 "It is not part of this application. If you have the file <tt>SLUS-20973_4028A55F_signin.pnach</tt>, put it into one of these folders and start again:<br>%1")
			             .arg(QString::fromStdString(info.signinPlaces).trimmed().toHtmlEscaped().replace("\n", "<br>"));
		auto signinLabel = new QLabel(signin, &dialog);
		signinLabel->setWordWrap(true);
		signinLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
		form->addRow("Sign-in patch:", signinLabel);

		if(info.packaged)
		{
			// a path has no place to break a line at: the name, and the folder shortened in the middle
			QString discText = "none chosen yet";
			if(!info.disc.empty())
			{
				QFileInfo file(QString::fromStdString(info.disc));
				discText = file.fileName() + "\nin " + dialog.fontMetrics().elidedText(file.absolutePath(), Qt::ElideMiddle, 400);
			}
			auto disc = new QLabel(discText, &dialog);
			disc->setTextFormat(Qt::PlainText);
			disc->setToolTip(QString::fromStdString(info.disc));
			disc->setTextInteractionFlags(Qt::TextSelectableByMouse);
			form->addRow("Disc image:", disc);
		}
		else
		{
			auto note = new QLabel("This copy was started by play.sh: the server and the player are its --server and --player options.", &dialog);
			note->setWordWrap(true);
			layout->addWidget(note);
		}

		auto buttons = new QDialogButtonBox(info.packaged ? (QDialogButtonBox::Save | QDialogButtonBox::Cancel) : QDialogButtonBox::Close, &dialog);
		QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
		QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
		layout->addWidget(buttons);
		result.server = server;
		result.player = player;
		return result;
	}
}

void Rta::ShowOnline(QWidget* parent)
{
	auto info = Rta::GetLaunchInfo();
	auto online = BuildOnline(parent, info);
	std::unique_ptr<QDialog> dialog(online.dialog);
	if(dialog->exec() != QDialog::Accepted || !info.packaged) return;

	std::string newServer = online.server->text().trimmed().toStdString();
	int newPlayer = online.player->value();
	if(newServer == info.server && newPlayer == info.player) return;
	Rta::SaveLaunch(newServer, newPlayer);
	auto answer = QMessageBox::question(parent, "Online", "The change is taken up when the application starts again. The game that is running ends.\n\nStart again now?", QMessageBox::Yes | QMessageBox::No);
	if(answer == QMessageBox::Yes) Rta::Relaunch();
}

// For tests: a picture of one of our windows as it would be shown, without showing it
// to anyone ("controls", "online", "about" - the text only for the last).
bool Rta::RenderDialog(const std::string& name, const std::string& path)
{
	QWidget* parent = g_mainWindow;
	if(name == "online")
	{
		auto online = BuildOnline(parent, Rta::GetLaunchInfo());
		std::unique_ptr<QDialog> dialog(online.dialog);
		dialog->setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog->show();
		bool saved = dialog->grab().save(QString::fromStdString(path), "PNG");
		dialog->hide();
		return saved;
	}
	if(name == "controls" || name == "about")
	{
		QDialog dialog(parent);
		auto layout = new QVBoxLayout(&dialog);
		auto label = new QLabel((name == "controls") ? ControlsText() : QString::fromStdString(Rta::AboutText()).trimmed(), &dialog);
		label->setTextFormat((name == "controls") ? Qt::RichText : Qt::PlainText);
		label->setWordWrap(true);
		label->setMinimumWidth(520);
		layout->addWidget(label);
		dialog.setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog.show();
		bool saved = dialog.grab().save(QString::fromStdString(path), "PNG");
		dialog.hide();
		return saved;
	}
	return false;
}

void Rta::SetupWindow(QWidget* window)
{
	auto mainWindow = qobject_cast<QMainWindow*>(window);
	if(!mainWindow) return;
	g_mainWindow = mainWindow;
	{
		auto onlineMenu = new QMenu("Online", mainWindow);
		auto helpAction = mainWindow->findChild<QMenu*>("menuHelp") ? mainWindow->findChild<QMenu*>("menuHelp")->menuAction() : nullptr;
		mainWindow->menuBar()->insertMenu(helpAction, onlineMenu);
		auto settings = onlineMenu->addAction("Server, player, patch set...");
		settings->setMenuRole(QAction::NoRole);
		QObject::connect(settings, &QAction::triggered, mainWindow, [mainWindow]() { Rta::ShowOnline(mainWindow); });
		if(Rta::GetLaunchInfo().packaged)
		{
			auto disc = onlineMenu->addAction("Choose the disc image...");
			disc->setMenuRole(QAction::NoRole);
			QObject::connect(disc, &QAction::triggered, mainWindow, [mainWindow]() { Rta::BootDisc(Rta::ChooseDisc(mainWindow, std::string(), true)); });
		}
	}
	auto helpMenu = mainWindow->findChild<QMenu*>("menuHelp");
	if(!helpMenu) helpMenu = mainWindow->menuBar()->addMenu("Help");
	auto controls = new QAction("Controls...", mainWindow);
	controls->setMenuRole(QAction::NoRole);
	QObject::connect(controls, &QAction::triggered, mainWindow, [mainWindow]() { Rta::ShowControls(mainWindow); });
	helpMenu->insertAction(helpMenu->actions().isEmpty() ? nullptr : helpMenu->actions().first(), controls);

	// once per data directory, a moment after the first start: the keys. Not in test runs.
	auto& config = CAppConfig::GetInstance();
	config.RegisterPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, false);
	if(!config.GetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN) && !Rta::IsTestRun())
	{
		config.SetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, true);
		QTimer::singleShot(2500, mainWindow, [mainWindow]() { Rta::ShowControls(mainWindow); });
	}
}
